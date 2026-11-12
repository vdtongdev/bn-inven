from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest

from app.db import SessionLocal
from app.main import app
from app.models import CaptureBatch, CatalogItem, ProductDraft


@pytest.fixture
def approved_item():
    with SessionLocal() as db:
        batch = CaptureBatch(name="Edit approved product")
        db.add(batch)
        db.flush()
        draft = ProductDraft(batch_id=batch.id, item_code=f"BN-{batch.id}",
                             product_type="Sữa", product_name="Ít đường", brand="TH",
                             primary_unit="Hộp", package_size="1 L")
        db.add(draft)
        db.commit()
        draft_id = draft.id
    with TestClient(app) as client:
        response = client.post(f"/api/drafts/{draft_id}/approve")
        assert response.status_code == 200
        yield client, response.json()


def test_edit_approved_updates_catalog_history_and_future_exports(approved_item):
    client, original = approved_item
    profile = client.get("/api/export-profiles").json()[0]

    def export():
        response = client.post("/api/exports", json={
            "profile_id": profile["id"], "draft_ids": [original["id"]]})
        assert response.status_code == 201
        return f"/api/exports/{response.json()['id']}/download"

    old_export = export()
    old_bytes = client.get(old_export).content
    url = f"/api/drafts/{original['id']}"
    patch = {"product_type": " Sữa tươi ", "brand": "Vinamilk", "product_name": "Không đường",
             "primary_unit": "Chai", "package_size": "500 ml", "barcode": "NEW-123",
             "model_number": "MODEL-2", "category_code": "MILK"}
    edited = client.patch(url, json=patch)
    assert edited.status_code == 200
    updated = edited.json()
    expected = "Sữa tươi Vinamilk Không đường Chai 500 ml"
    assert updated["final_name"] == expected
    assert updated["review_status"] == "Approved"
    assert updated["item_code"] == original["item_code"]
    assert updated["matched_catalog_item_id"] == original["matched_catalog_item_id"]
    with SessionLocal() as db:
        catalog = db.get(CatalogItem, original["matched_catalog_item_id"])
        assert catalog.product_name == expected
        for field in ("brand", "primary_unit", "package_size", "barcode", "model_number", "category_code"):
            assert getattr(catalog, field) == patch[field]
    events = client.get(f"{url}/history").json()
    assert events[-1]["action"] == "edited"
    assert events[-1]["changes"]["product_name"]["after"] == "Không đường"
    assert "review_status" not in events[-1]["changes"]
    assert client.patch(url, json=patch).json()["final_name"] == expected
    assert len(client.get(f"{url}/history").json()) == len(events)
    assert client.post(f"{url}/approve").json()["final_name"] == expected
    content = client.get(export()).content
    assert load_workbook(BytesIO(content)).active.cell(2, 2).value == expected
    assert client.get(old_export).content == old_bytes


@pytest.mark.parametrize("patch", [
    {"primary_unit": " "},
    {"product_type": None, "product_name": "", "brand": None},
])
def test_invalid_approved_edit_preserves_saved_values(approved_item, patch):
    client, original = approved_item
    url = f"/api/drafts/{original['id']}"
    events = client.get(f"{url}/history").json()
    assert client.patch(url, json=patch).status_code == 422
    saved = client.get(f"/api/batches/{original['batch_id']}/drafts").json()[0]
    assert saved == original
    assert client.get(f"{url}/history").json() == events
    with SessionLocal() as db:
        catalog = db.get(CatalogItem, original["matched_catalog_item_id"])
        assert catalog.product_name == original["final_name"]
        assert catalog.primary_unit == original["primary_unit"]
