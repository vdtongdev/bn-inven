"""Dependency-free regression checks for findings from the initial review.

These assertions intentionally fail until the architecture/security findings are fixed.
They inspect source/config so they can run before backend/frontend dependencies are installed.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class VerifierRegressionTests(unittest.TestCase):
    def test_public_web_service_is_not_published_outside_caddy(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        web_service = compose.split("  web:", 1)[1].split("  caddy:", 1)[0]
        api_service = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
        caddy_service = compose.split("  caddy:", 1)[1].split("volumes:", 1)[0]
        caddy = (ROOT / "infra/Caddyfile").read_text(encoding="utf-8")
        self.assertNotIn("ports:", web_service)
        self.assertNotIn("ports:", api_service)
        self.assertNotIn('profiles: ["https"]', caddy_service)
        self.assertIn('"80:80"', caddy_service)
        self.assertIn('"443:443"', caddy_service)
        self.assertIn("basic_auth", caddy)
        self.assertIn("reverse_proxy api:8000", caddy)

    def test_production_entrypoints_do_not_create_schema_implicitly(self):
        main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        db = (ROOT / "backend/app/db.py").read_text(encoding="utf-8")
        worker = (ROOT / "backend/app/workers/extraction.py").read_text(encoding="utf-8")
        migration = (ROOT / "backend/alembic/versions/0001_initial.py").read_text(encoding="utf-8")
        self.assertNotIn("initialize_database()", main)
        self.assertNotIn("initialize_database()", worker)
        self.assertNotIn("create_all", db)
        self.assertNotIn("Base.metadata.create_all", migration)
        self.assertNotIn("Base.metadata.drop_all", migration)
        self.assertIn("op.create_table", migration)
        self.assertIn('"capture_batches"', migration)
        self.assertIn('"product_drafts"', migration)

    def test_batch_barcode_duplicates_can_reach_review_matching(self):
        models = (ROOT / "backend/app/models.py").read_text(encoding="utf-8")
        worker = (ROOT / "backend/app/workers/extraction.py").read_text(encoding="utf-8")
        self.assertNotIn('UniqueConstraint("batch_id", "barcode"', models)
        self.assertIn("duplicate_suggestion", models)
        self.assertIn("duplicate", worker.lower())
        self.assertIn("barcode", worker)

    def test_shared_access_token_is_not_referenced_by_frontend_bundle(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "frontend").rglob("*")
            if path.is_file() and not {"node_modules", "dist"}.intersection(path.parts)
        )
        self.assertNotIn("VITE_APP_ACCESS_TOKEN", source)
        self.assertNotIn("APP_ACCESS_TOKEN", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
