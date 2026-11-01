from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image
import pytest
from sqlalchemy import inspect
from sqlalchemy import create_engine

from app.ai.providers import MockVisionProvider, ProviderResult
from app.ai.prompts import PROMPT_VERSION
from app.ai.openrouter import ProviderPermanentError, ProviderTransientError
from app.db import SessionLocal
from app.db import engine
from app.main import app
from app.models import CatalogItem, ExtractionJob, ExtractionResult, JobStatus
from app.schemas import ExtractionPayload
from app.workers.extraction import process_one


def image_bytes(color="white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 64), color).save(output, format="PNG")
    return output.getvalue()


def test_extraction_schema_is_strict_and_nullable():
    assert ExtractionPayload().product_name is None
    try:
        ExtractionPayload(product_name="ok", unexpected="invented")
    except ValueError:
        pass
    else:
        raise AssertionError("extra extraction fields must be rejected")


def test_initial_alembic_revision_creates_expected_tables():
    tables = set(inspect(engine).get_table_names())
    assert {"capture_batches", "product_photos", "extraction_jobs", "extraction_results",
            "product_drafts", "catalog_items", "misa_export_profiles", "export_runs"} <= tables


def test_fresh_sqlite_migration_creates_nullable_photo_draft_foreign_key(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    database_path = tmp_path / "fresh-migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        get_settings.cache_clear()

    migration_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        schema = inspect(migration_engine)
        columns = {column["name"]: column for column in schema.get_columns("product_photos")}
        assert "draft_id" in columns
        assert columns["draft_id"]["nullable"] is True
        assert any(
            foreign_key["constrained_columns"] == ["draft_id"]
            and foreign_key["referred_table"] == "product_drafts"
            and foreign_key["referred_columns"] == ["id"]
            and foreign_key["options"].get("ondelete") == "SET NULL"
            for foreign_key in schema.get_foreign_keys("product_photos")
        )
        assert any(
            index["name"] == "ix_product_photos_draft_id"
            and index["column_names"] == ["draft_id"]
            for index in schema.get_indexes("product_photos")
        )
    finally:
        migration_engine.dispose()


def test_durable_job_review_approval_and_demo_export():
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Lô tháng 10"}).json()
        upload = client.post(f"/api/batches/{batch['id']}/photos", files={"file": ("label.png", image_bytes(), "image/png")})
        assert upload.status_code == 202
        job_id = upload.json()["job_id"]
        duplicate_upload = client.post(f"/api/batches/{batch['id']}/photos", files={"file": ("copy.png", image_bytes(), "image/png")})
        assert duplicate_upload.json()["job_id"] == job_id
        with SessionLocal() as db:
            job = db.get(ExtractionJob, job_id)
            assert job is not None and job.status == JobStatus.queued
        assert process_one() is True
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "Succeeded" and job["draft_id"]
        draft_id = job["draft_id"]
        assert client.post(f"/api/drafts/{draft_id}/approve").status_code == 422
        extra_photo = client.post(f"/api/batches/{batch['id']}/photos",
            data={"draft_id": draft_id}, files={"file": ("side.png", image_bytes("navy"), "image/png")})
        assert extra_photo.status_code == 202
        assert process_one() is True
        after_second_photo = client.get(f"/api/batches/{batch['id']}/drafts").json()
        assert len(after_second_photo) == 1
        assert len(after_second_photo[0]["photo_ids"]) == 2
        edited = client.patch(f"/api/drafts/{draft_id}", json={
            "product_name": "  Bút bi xanh  ", "item_type": "Hàng hóa", "primary_unit": "cây"
        })
        assert edited.status_code == 200
        approved = client.post(f"/api/drafts/{draft_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["review_status"] == "Approved"
        profile = client.get("/api/export-profiles").json()[0]
        exported = client.post("/api/exports", json={"profile_id": profile["id"], "draft_ids": [draft_id]})
        assert exported.status_code == 201
        content = client.get(f"/api/exports/{exported.json()['id']}/download").content
        sheet = load_workbook(BytesIO(content), read_only=True).active
        assert sheet["A2"].value.startswith("BN-")
        assert sheet["B2"].value == "Bút bi xanh"


def test_mock_provider_does_not_invent_label_facts(tmp_path):
    result = MockVisionProvider().extract(tmp_path / "missing-is-not-read-by-mock.png")
    assert result.payload.product_name is None
    assert result.provider == "mock"


def test_worker_preserves_provider_usage_trace(monkeypatch):
    class TracedProvider:
        def extract(self, _image_path):
            payload = ExtractionPayload()
            return ProviderResult(payload, "openrouter", "test-model", {
                "provider_response": {"usage": {"total_tokens": 17, "cost": 0.001}},
                "usage": {"total_tokens": 17, "cost": 0.001},
                "prompt_version": PROMPT_VERSION,
            })

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: TracedProvider())
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Trace check"}).json()
        uploaded = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("trace.png", image_bytes(), "image/png")})
        assert uploaded.status_code == 202
        assert process_one() is True
        with SessionLocal() as db:
            trace = db.query(ExtractionResult).filter_by(job_id=uploaded.json()["job_id"]).one()
            assert trace.provider == "openrouter"
            assert trace.model == "test-model"
            assert trace.prompt_version == PROMPT_VERSION
            assert trace.raw_response["usage"]["total_tokens"] == 17
            assert trace.raw_response["usage"]["cost"] == 0.001


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_attempts"),
    [(ProviderPermanentError("secret-safe failure"), JobStatus.failed, 1),
     (ProviderTransientError("retry-safe failure"), JobStatus.queued, 1)],
)
def test_worker_classifies_provider_failures_and_sanitizes_job_error(
    monkeypatch, error, expected_status, expected_attempts
):
    class FailingProvider:
        def extract(self, _image_path):
            raise error

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: FailingProvider())
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Failure check"}).json()
        uploaded = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("failure.png", image_bytes(), "image/png")})
        job_id = uploaded.json()["job_id"]
        assert process_one() is True
        with SessionLocal() as db:
            job = db.get(ExtractionJob, job_id)
            assert job.status == expected_status
            assert job.attempts == expected_attempts
            assert job.last_error == error.public_message


def test_exact_barcode_matches_are_suggestions_not_merges(monkeypatch):
    class BarcodeProvider:
        def __init__(self, barcode):
            self.barcode = barcode

        def extract(self, _image_path):
            payload = ExtractionPayload(product_name="Widget", barcode=self.barcode)
            return ProviderResult(payload, "test", "fixed-barcode", payload.model_dump())

    with SessionLocal() as db:
        catalog_item = CatalogItem(item_code="CAT-MATCH-1", product_name="Catalog widget",
            item_type="Hàng hóa", primary_unit="cái", barcode="CAT-123")
        db.add(catalog_item)
        db.commit()
        catalog_id = catalog_item.id

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: BarcodeProvider("CAT-123"))
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Catalog duplicate"}).json()
        uploaded = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("catalog.png", image_bytes("red"), "image/png")})
        assert uploaded.status_code == 202
        assert process_one() is True
        catalog_draft = client.get(f"/api/batches/{batch['id']}/drafts").json()[0]
        assert catalog_draft["review_status"] == "Pending"
        assert catalog_draft["duplicate_suggestion"] == {
            "kind": "exact_barcode", "scope": "catalog", "target_id": catalog_id,
            "item_code": "CAT-MATCH-1", "requires_human_review": True,
        }

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: BarcodeProvider("BATCH-123"))
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Batch duplicate"}).json()
        first = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("first.png", image_bytes("green"), "image/png")})
        assert first.status_code == 202 and process_one() is True
        second = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("second.png", image_bytes("blue"), "image/png")})
        assert second.status_code == 202 and process_one() is True
        drafts = client.get(f"/api/batches/{batch['id']}/drafts").json()
        assert len(drafts) == 2
        suggestion = next(d["duplicate_suggestion"] for d in drafts if d["duplicate_suggestion"])
        target = next(d for d in drafts if d["id"] == suggestion["target_id"])
        assert suggestion["kind"] == "exact_barcode"
        assert suggestion["scope"] == "batch_draft"
        assert suggestion["item_code"] == target["item_code"]
        assert all(d["review_status"] == "Pending" for d in drafts)
