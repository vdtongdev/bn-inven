from fastapi.testclient import TestClient
from openpyxl import load_workbook
from io import BytesIO

from app.db import SessionLocal
from app.main import app
from app.models import CaptureBatch, ProductDraft, CatalogItem
from app.product_names import compose_product_name
import pytest


@pytest.mark.parametrize("parts, expected", [
    (("Sữa", "Vinamilk", None, "Hộp", "1 L"), "Sữa Vinamilk Hộp 1 L"),
    (("Sữa", "Vinamilk", " VINAMILK ", "Hộp", "1 L"), "Sữa Vinamilk Hộp 1 L"),
    (("Sữa", "Vinamilk", "Su\u031b\u0303a", "Hộp", "1 L"), "Sữa Vinamilk Hộp 1 L"),
    ((None, "Vinamilk", "Ít đường", "Hộp", "1 L"), "Vinamilk Ít đường Hộp 1 L"),
    ((None, None, None, "Hộp", "1 L"), None),
    (("  Sữa   tươi ", None, "Ít đường", None, None), "Sữa tươi Ít đường"),
])
def test_name_format(parts, expected):
    assert compose_product_name(*parts) == expected


def test_edited_components_persist_final_name_through_approval_and_export():
    with SessionLocal() as db:
        batch = CaptureBatch(name="Title regression")
        db.add(batch)
        db.flush()
        draft = ProductDraft(batch_id=batch.id, item_code=f"BN-{batch.id}", product_name="Vinamilk")
        db.add(draft)
        db.commit()
        draft_id, batch_id = draft.id, batch.id
    with TestClient(app) as client:
        url = f"/api/drafts/{draft_id}"
        edited = client.patch(url, json={"product_type": "Sữa", "brand": "Vinamilk",
                                        "primary_unit": "Hộp", "package_size": "1 L"})
        assert edited.status_code == 200
        assert edited.json().get("product_type") == "Sữa"
        assert edited.json()["final_name"] == "Sữa Vinamilk Hộp 1 L"
        # Repeated saves never concatenate the previously composed name again.
        edited = client.patch(url, json={"product_name": "Ít đường", "package_size": "500 ml"})
        expected = "Sữa Vinamilk Ít đường Hộp 500 ml"
        assert edited.json()["final_name"] == expected
        assert client.patch(url, json={"product_name": "Ít đường"}).json()["final_name"] == expected
        assert client.get(f"/api/batches/{batch_id}/drafts").json()[0]["final_name"] == expected
        approved = client.post(f"{url}/approve")
        assert approved.status_code == 200
        with SessionLocal() as db:
            saved = db.get(ProductDraft, draft_id)
            assert saved.product_type == "Sữa"
            assert saved.final_name == expected
            assert db.get(CatalogItem, saved.matched_catalog_item_id).product_name == expected
        profile = client.get('/api/export-profiles').json()[0]
        exported = client.post('/api/exports', json={"profile_id": profile["id"], "draft_ids": [draft_id]})
        assert exported.status_code == 201
        content = client.get(f"/api/exports/{exported.json()['id']}/download").content
        assert load_workbook(BytesIO(content)).active.cell(2, 2).value == expected


def test_extraction_populates_editable_type_and_preserves_human_corrections(monkeypatch):
    from PIL import Image
    from app.ai.providers import ProviderResult
    from app.schemas import ExtractionPayload
    from app.workers.extraction import process_one

    class Provider:
        def extract(self, _path):
            payload = ExtractionPayload(product_type="Sữa", product_name="Vinamilk", brand="Vinamilk",
                                        unit_suggestion="Hộp", package_size="1 L")
            return ProviderResult(payload, "test", "test", payload.model_dump())

    monkeypatch.setattr("app.workers.extraction.get_provider", lambda _: Provider())
    with TestClient(app) as client:
        batch_id = client.post('/api/batches', json={"name": "Type extraction"}).json()["id"]
        for color in ("white", "blue"):
            output = BytesIO()
            Image.new("RGB", (32, 32), color).save(output, format="PNG")
            data = {"draft_id": draft_id} if color == "blue" else {}
            upload = client.post(f'/api/batches/{batch_id}/photos', data=data,
                                 files={"file": ("label.png", output.getvalue(), "image/png")})
            assert upload.status_code == 202
            assert process_one()
            draft = client.get(f'/api/batches/{batch_id}/drafts').json()[0]
            draft_id = draft["id"]
            if color == "white":
                assert draft["product_type"] == "Sữa"
                assert draft["final_name"] == "Sữa Vinamilk Hộp 1 L"
                client.patch(f'/api/drafts/{draft_id}', json={"product_type": "Sữa tươi", "product_name": ""})
            else:
                assert draft["product_type"] == "Sữa tươi"
                assert draft["product_name"] == ""
                assert draft["final_name"] == "Sữa tươi Vinamilk Hộp 1 L"


def test_name_migration_backfills_type_and_preserves_approved_names(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from alembic import command
    from alembic.config import Config
    import sqlalchemy as sa
    from app.core.config import get_settings

    database_url = f"sqlite:///{(tmp_path / 'names.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    migration_engine = sa.create_engine(database_url)
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "0002_product_draft_audit")
        tables = sa.MetaData()
        tables.reflect(migration_engine)
        now = datetime.now(timezone.utc)
        with migration_engine.begin() as connection:
            connection.execute(tables.tables['misa_export_profiles'].insert(), dict(
                id="legacy-demo", code="GENERIC_DEMO", name="DEMO", worksheet_name="Demo Items",
                start_row=2, column_mapping={"product_name": 1, "item_type": 2, "primary_unit": 3},
                required_fields=["product_name", "item_type", "primary_unit"],
                permitted_values={"item_type": ["Goods"]}, is_demo=True))
            connection.execute(tables.tables['catalog_items'].insert(), dict(
                id="catalog", item_code="catalog-code", product_name="Vinamilk", item_type="Goods",
                primary_unit="Hộp", created_at=now))
            connection.execute(tables.tables['capture_batches'].insert(),
                               dict(id="batch", name="Legacy", created_at=now))
            connection.execute(tables.tables['product_photos'].insert(), dict(
                id="photo", batch_id="batch", filename="label.png", content_type="image/png",
                byte_size=10, width=32, height=32, sha256="abc", created_at=now))
            connection.execute(tables.tables['extraction_jobs'].insert(), dict(
                id="job", photo_id="photo", status="succeeded", attempts=1, max_attempts=3,
                next_attempt_at=now, created_at=now, updated_at=now))
            connection.execute(tables.tables['extraction_results'].insert(), dict(
                id="result", job_id="job", photo_id="photo", schema_version="v1", provider="mock",
                model="mock", prompt_version="v1", raw_response={}, observed={"product_type": "Sữa"},
                suggestions={}, created_at=now))
            for state in ('pending', 'approved'):
                connection.execute(tables.tables['product_drafts'].insert(), dict(
                    id=state, batch_id="batch", item_code=state, product_name="Vinamilk",
                    brand="Vinamilk", primary_unit="Hộp", package_size="1 L", review_status=state,
                    matched_catalog_item_id="catalog" if state == 'approved' else None,
                    extraction_result_id="result" if state == 'pending' else None,
                    created_at=now, updated_at=now))
        command.upgrade(config, "head")
        with migration_engine.connect() as connection:
            rows = {row['id']: row for row in connection.execute(sa.text(
                'SELECT id, product_type, final_name FROM product_drafts')).mappings()}
            assert rows['pending']['product_type'] == "Sữa"
            assert rows['pending']['final_name'] == "Sữa Vinamilk Hộp 1 L"
            assert rows['approved']['final_name'] == "Vinamilk"
            assert connection.execute(sa.text('SELECT product_name FROM catalog_items')).scalar_one() == "Vinamilk"
            assert connection.execute(sa.text(
                "SELECT matched_catalog_item_id FROM product_drafts WHERE id = 'approved'"
            )).scalar_one() == "catalog"
            for table in ('catalog_items', 'product_drafts'):
                assert 'item_type' not in {column['name'] for column in sa.inspect(connection).get_columns(table)}
            profile_table = sa.Table('misa_export_profiles', sa.MetaData(), autoload_with=connection)
            profile = connection.execute(sa.select(profile_table)).mappings().one()
            assert profile['column_mapping'] == {"product_name": 1, "primary_unit": 2}
            assert profile['required_fields'] == ["product_name", "primary_unit"]
            assert profile['permitted_values'] == {}
        command.downgrade(config, "0002_product_draft_audit")
        command.upgrade(config, "head")
    finally:
        migration_engine.dispose()
        get_settings.cache_clear()
