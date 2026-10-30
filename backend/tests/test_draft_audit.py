import json
from datetime import datetime
from io import BytesIO

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.orm import Session

from app.ai.providers import ProviderResult
from app.core.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import CatalogItem, CaptureBatch, ProductDraft
from app.schemas import ExtractionPayload
from app.workers.extraction import process_one


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (48, 48), "white").save(output, format="PNG")
    return output.getvalue()


class FixedProvider:
    def extract(self, _image_path):
        payload = ExtractionPayload(product_name="AI name", brand="AI brand")
        return ProviderResult(
            payload,
            "test-provider",
            "test-model",
            {"raw_response": "private extraction trace", "api_key": "must-not-appear-in-history"},
        )


def create_draft(client, monkeypatch, batch_name="Audit test"):
    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: FixedProvider())
    batch = client.post("/api/batches", json={"name": batch_name}).json()
    uploaded = client.post(
        f"/api/batches/{batch['id']}/photos",
        files={"file": ("audit.png", image_bytes(), "image/png")},
    )
    assert uploaded.status_code == 202
    assert process_one() is True
    job = client.get(f"/api/jobs/{uploaded.json()['job_id']}").json()
    assert job["status"] == "Succeeded"
    return batch["id"], job["draft_id"]


def history(client, draft_id):
    return client.get(f"/api/drafts/{draft_id}/history")


def test_edit_noop_approval_and_history_are_chronological(monkeypatch):
    with TestClient(app) as client:
        _batch_id, draft_id = create_draft(client, monkeypatch)
        assert history(client, draft_id).status_code == 200
        assert history(client, draft_id).json() == []

        edited = client.patch(f"/api/drafts/{draft_id}", json={"product_name": "  Human name  "})
        assert edited.status_code == 200
        assert edited.json()["product_name"] == "Human name"
        first_history = history(client, draft_id).json()
        assert len(first_history) == 1
        assert first_history[0]["action"] == "edited"
        assert first_history[0]["changes"] == {
            "product_name": {"before": "AI name", "after": "Human name"},
            "review_status": {"before": "Pending", "after": "NeedsCorrection"},
        }

        # The same value on an already corrected draft is a true no-op.
        assert client.patch(f"/api/drafts/{draft_id}", json={"product_name": "Human name"}).status_code == 200
        assert len(history(client, draft_id).json()) == 1

        second_edit = client.patch(f"/api/drafts/{draft_id}", json={
            "item_type": " Goods ", "primary_unit": " each "
        })
        assert second_edit.status_code == 200
        item_code = second_edit.json()["item_code"]
        assert client.post(f"/api/drafts/{draft_id}/approve").status_code == 200
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CatalogItem).where(
                CatalogItem.item_code == item_code
            )) == 1

        events = history(client, draft_id).json()
        assert [event["action"] for event in events] == ["edited", "edited", "approved"]
        assert events[1]["changes"] == {
            "item_type": {"before": None, "after": "Goods"},
            "primary_unit": {"before": None, "after": "each"},
        }
        assert events[2]["changes"]["review_status"] == {
            "before": "NeedsCorrection", "after": "Approved"
        }
        timestamps = [datetime.fromisoformat(event["created_at"]) for event in events]
        assert timestamps == sorted(timestamps)
        ordered_keys = [(event["created_at"], event["id"]) for event in events]
        assert ordered_keys == sorted(ordered_keys)
        serialized = json.dumps(events)
        assert "raw_response" not in serialized
        assert "test-provider" not in serialized
        assert "must-not-appear-in-history" not in serialized


def test_exclusion_invalid_approval_and_unknown_history(monkeypatch):
    with TestClient(app) as client:
        _batch_id, excluded_draft_id = create_draft(client, monkeypatch, "Exclude test")
        excluded = client.patch(f"/api/drafts/{excluded_draft_id}", json={"review_status": "Excluded"})
        assert excluded.status_code == 200
        excluded_history = history(client, excluded_draft_id)
        assert excluded_history.status_code == 200
        assert len(excluded_history.json()) == 1
        event = excluded_history.json()[0]
        assert event["action"] == "excluded"
        assert event["changes"] == {
            "review_status": {"before": "Pending", "after": "Excluded"}
        }

        invalid_batch_id, invalid_draft_id = create_draft(client, monkeypatch, "Invalid approval")
        assert client.post(f"/api/drafts/{invalid_draft_id}/approve").status_code == 422
        assert history(client, invalid_draft_id).json() == []
        invalid_draft = client.get(f"/api/batches/{invalid_batch_id}/drafts").json()[0]
        assert invalid_draft["review_status"] == "Pending"
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CatalogItem).where(
                CatalogItem.item_code == invalid_draft["item_code"]
            )) == 0
        assert history(client, "missing-draft-id").status_code == 404


def test_audit_events_cascade_when_draft_or_batch_is_deleted(monkeypatch):
    with TestClient(app) as client:
        batch_id, draft_id = create_draft(client, monkeypatch, "Draft deletion")
        assert client.patch(f"/api/drafts/{draft_id}", json={"product_name": "Edited"}).status_code == 200
        assert len(history(client, draft_id).json()) == 1
        with SessionLocal() as db:
            db.execute(delete(ProductDraft).where(ProductDraft.id == draft_id))
            db.commit()
            assert db.scalar(text(
                "SELECT count(*) FROM draft_audit_events WHERE draft_id = :draft_id"
            ), {"draft_id": draft_id}) == 0

        batch_id, second_draft_id = create_draft(client, monkeypatch, "Batch deletion")
        assert client.patch(f"/api/drafts/{second_draft_id}", json={"product_name": "Edited"}).status_code == 200
        with SessionLocal() as db:
            db.execute(delete(CaptureBatch).where(CaptureBatch.id == batch_id))
            db.commit()
            assert db.scalar(text(
                "SELECT count(*) FROM draft_audit_events WHERE draft_id = :draft_id"
            ), {"draft_id": second_draft_id}) == 0


def test_failed_approval_transaction_keeps_draft_catalog_and_history_unchanged(monkeypatch):
    with TestClient(app, raise_server_exceptions=False) as client:
        _batch_id, draft_id = create_draft(client, monkeypatch, "Rollback test")
        edited = client.patch(f"/api/drafts/{draft_id}", json={
            "item_type": "Goods", "primary_unit": "each"
        })
        item_code = edited.json()["item_code"]
        before_history = history(client, draft_id).json()
        before_catalog_count = None
        with SessionLocal() as db:
            before_catalog_count = db.scalar(select(func.count()).select_from(CatalogItem).where(
                CatalogItem.item_code == item_code
            ))

        def fail_commit(_session):
            raise RuntimeError("simulated commit failure")

        original_commit = Session.commit
        monkeypatch.setattr(Session, "commit", fail_commit)
        try:
            response = client.post(f"/api/drafts/{draft_id}/approve")
        finally:
            monkeypatch.setattr(Session, "commit", original_commit)
        assert response.status_code == 500
        assert history(client, draft_id).json() == before_history
        with SessionLocal() as db:
            draft = db.get(ProductDraft, draft_id)
            assert draft.review_status.value == "NeedsCorrection"
            assert db.scalar(select(func.count()).select_from(CatalogItem).where(
                CatalogItem.item_code == item_code
            )) == before_catalog_count == 0


def test_audit_migration_upgrade_downgrade_and_reupgrade(tmp_path, monkeypatch):
    database_path = tmp_path / "audit-migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
        migration_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        try:
            schema = inspect(migration_engine)
            assert "draft_audit_events" in schema.get_table_names()
            assert any(
                fk["constrained_columns"] == ["draft_id"]
                and fk["referred_table"] == "product_drafts"
                and fk["options"].get("ondelete") == "CASCADE"
                for fk in schema.get_foreign_keys("draft_audit_events")
            )
            assert any(
                index["column_names"] == ["draft_id", "created_at"]
                for index in schema.get_indexes("draft_audit_events")
            )
        finally:
            migration_engine.dispose()

        command.downgrade(config, "0001_initial")
        migration_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        try:
            assert "draft_audit_events" not in inspect(migration_engine).get_table_names()
        finally:
            migration_engine.dispose()
        command.upgrade(config, "head")
        migration_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        try:
            assert "draft_audit_events" in inspect(migration_engine).get_table_names()
        finally:
            migration_engine.dispose()
    finally:
        get_settings.cache_clear()
