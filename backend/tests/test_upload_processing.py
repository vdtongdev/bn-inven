from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.ai.providers import ProviderResult
from app.db import SessionLocal
from app.main import app
from app.models import ExtractionJob
from app.schemas import ExtractionPayload
from app.workers.extraction import process_one


def photo_bytes(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), color).save(output, format="PNG")
    return output.getvalue()


def test_additional_photo_success_exposes_its_extraction_on_the_product(monkeypatch):
    payloads = iter([
        ExtractionPayload(product_name="Label front"),
        ExtractionPayload(product_name="Label front", brand="Visible on back"),
    ])

    class Provider:
        def extract(self, _path):
            payload = next(payloads)
            return ProviderResult(payload, "test", "two-labels", payload.model_dump())

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: Provider())
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Additional photo regression"}).json()
        first = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("front.png", photo_bytes("orange"), "image/png")}).json()
        assert process_one() is True
        draft_id = client.get(f"/api/jobs/{first['job_id']}").json()["draft_id"]
        second = client.post(f"/api/batches/{batch['id']}/photos", data={"draft_id": draft_id},
            files={"file": ("back.png", photo_bytes("purple"), "image/png")}).json()
        assert process_one() is True
        job = client.get(f"/api/jobs/{second['job_id']}").json()
        assert job["status"] == "Succeeded"
        draft = client.get(f"/api/batches/{batch['id']}/drafts").json()[0]
        assert draft["extraction"]["observed"]["brand"] == "Visible on back"
        assert draft["brand"] == "Visible on back"
        assert draft["product_name"] == "Label front"
        assert draft["review_status"] == "Pending"
        assert job["draft_id"] == draft_id
        assert client.get(f"/api/jobs/{first['job_id']}").json()["draft_id"] == draft_id
        with SessionLocal() as db:
            assert db.get(ExtractionJob, first["job_id"]).result.observed["product_name"] == "Label front"


def test_reupload_after_exclusion_produces_a_visible_review_product():
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Excluded reupload regression"}).json()
        data = photo_bytes("brown")
        first = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("first.png", data, "image/png")}).json()
        assert process_one() is True
        draft_id = client.get(f"/api/jobs/{first['job_id']}").json()["draft_id"]
        assert client.patch(f"/api/drafts/{draft_id}", json={"review_status": "Excluded"}).status_code == 200
        second = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("again.png", data, "image/png")}).json()
        assert second["job_id"] != first["job_id"]
        assert process_one() is True
        second_job = client.get(f"/api/jobs/{second['job_id']}").json()
        assert second_job["status"] == "Succeeded"
        assert second_job["draft_id"] != draft_id
        drafts = client.get(f"/api/batches/{batch['id']}/drafts").json()
        assert next(draft for draft in drafts if draft["id"] == draft_id)["review_status"] == "Excluded"
        assert next(draft for draft in drafts if draft["id"] == second_job["draft_id"])["review_status"] == "Pending"
        third = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("once-more.png", data, "image/png")}).json()
        assert third["job_id"] == second["job_id"]


def test_additional_photo_preserves_human_edits_including_empty_fields(monkeypatch):
    class Provider:
        def extract(self, _path):
            payload = ExtractionPayload(product_name="AI name", brand="AI brand")
            return ProviderResult(payload, "test", "human-edits", payload.model_dump())

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: Provider())
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Preserve human review"}).json()
        first = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("front.png", photo_bytes("gold"), "image/png")}).json()
        assert process_one() is True
        draft_id = client.get(f"/api/jobs/{first['job_id']}").json()["draft_id"]
        assert client.patch(f"/api/drafts/{draft_id}", json={
            "product_name": "HUMAN iPhone X", "brand": None, "primary_unit": "BOX"
        }).status_code == 200
        second = client.post(f"/api/batches/{batch['id']}/photos", data={"draft_id": draft_id},
            files={"file": ("back.png", photo_bytes("silver"), "image/png")}).json()
        assert process_one() is True
        assert client.get(f"/api/jobs/{second['job_id']}").json()["draft_id"] == draft_id
        draft = client.get(f"/api/batches/{batch['id']}/drafts").json()[0]
        assert draft["product_name"] == "HUMAN iPhone X"
        assert draft["primary_unit"] == "BOX"
        assert draft["brand"] is None
        assert draft["review_status"] == "NeedsCorrection"
        assert draft["extraction"]["observed"]["brand"] == "Ai brand"


def test_new_ai_results_normalize_drafts_and_observations_but_keep_raw_evidence(monkeypatch):
    original = {
        "product_name": "ĐÈN CHIẾU SÁNG", "product_type": "ĐÈN", "brand": "ACME",
        "unit_suggestion": "BOX", "model_number": "LED-XyZ", "barcode": "AbC0123",
        "category_suggestion": "CAT_LED", "package_size": "10 kW / 220 V",
        "attributes": {"serial": "aBcD", "power": 10},
        "confidence": {"product_name": 0.9},
    }

    class Provider:
        def extract(self, _path):
            return ProviderResult(ExtractionPayload(**original), "test", "mixed-case", original)

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _name: Provider())
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "AI normalization"}).json()
        upload = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("label.png", photo_bytes("lime"), "image/png")}).json()
        assert process_one() is True
        draft = client.get(f"/api/batches/{batch['id']}/drafts").json()[0]
        assert draft["product_name"] == "Đèn chiếu sáng"
        assert draft["brand"] == "Acme"
        assert draft["primary_unit"] == "Hộp"
        assert draft["model_number"] == "LED-XyZ"
        assert draft["barcode"] == "AbC0123"
        assert draft["category_code"] == "CAT_LED"
        assert draft["package_size"] == "10 kW / 220 V"
        assert draft["review_status"] == "Pending"
        observed = draft["extraction"]["observed"]
        assert observed["product_name"] == "Đèn chiếu sáng"
        assert observed["product_type"] == "Đèn"
        assert observed["attributes"] == original["attributes"]
        assert draft["extraction"]["suggestions"]["primary_unit"] == "Hộp"
        with SessionLocal() as db:
            result = db.get(ExtractionJob, upload["job_id"]).result
            assert result.raw_response == original
            assert result.prompt_version == "catalog-v5"


def test_duplicate_photo_is_not_redirected_to_another_product():
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Duplicate target"}).json()
        first = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("one.png", photo_bytes("red"), "image/png")}).json()
        assert process_one() is True
        second = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("two.png", photo_bytes("blue"), "image/png")}).json()
        assert process_one() is True
        target_id = client.get(f"/api/jobs/{second['job_id']}").json()["draft_id"]
        extra = client.post(f"/api/batches/{batch['id']}/photos", data={"draft_id": target_id},
            files={"file": ("same-as-one.png", photo_bytes("red"), "image/png")}).json()
        assert extra["job_id"] != first["job_id"]
        assert process_one() is True
        assert client.get(f"/api/jobs/{extra['job_id']}").json()["draft_id"] == target_id


def test_exclusion_during_recognition_does_not_report_visible_success():
    with TestClient(app) as client:
        batch = client.post("/api/batches", json={"name": "Exclude pending photo"}).json()
        first = client.post(f"/api/batches/{batch['id']}/photos",
            files={"file": ("front.png", photo_bytes("teal"), "image/png")}).json()
        assert process_one() is True
        draft_id = client.get(f"/api/jobs/{first['job_id']}").json()["draft_id"]
        second = client.post(f"/api/batches/{batch['id']}/photos", data={"draft_id": draft_id},
            files={"file": ("back.png", photo_bytes("pink"), "image/png")}).json()
        assert client.patch(f"/api/drafts/{draft_id}", json={"review_status": "Excluded"}).status_code == 200
        assert process_one() is True
        job = client.get(f"/api/jobs/{second['job_id']}").json()
        assert job["status"] == "Failed"
        assert "excluded" in job["last_error"]
        rejected = client.post(f"/api/batches/{batch['id']}/photos", data={"draft_id": draft_id},
            files={"file": ("back.png", photo_bytes("pink"), "image/png")})
        assert rejected.status_code == 409
