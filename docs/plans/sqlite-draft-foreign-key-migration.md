# Plan: Fix SQLite draft-photo migration

## Goal

Make the initial Alembic migration succeed on SQLite while preserving the `ProductPhoto.draft_id` relationship, `SET NULL` delete behavior, and lookup index. Keep schema creation explicit through Alembic and limit changes to this migration failure.

## Tasks

1. **Add a focused migration regression test.**
   - Agent: implementer
   - Add or extend a test that creates a fresh temporary SQLite database, runs `alembic upgrade head`, and inspects `product_photos`.
   - Assert that `draft_id` exists, references `product_drafts.id` with `ON DELETE SET NULL`, and has the `ix_product_photos_draft_id` index.
   - Run the test before the migration fix and confirm it reproduces the SQLite migration failure.

2. **Make the migration SQLite-compatible.**
   - Agent: implementer
   - Update `backend/alembic/versions/0001_initial.py` to add `product_photos.draft_id` and its index using SQLite-compatible Alembic batch operations, preserving the nullable column and `ON DELETE SET NULL` behavior.
   - Keep the migration explicit; do not add `Base.metadata.create_all` or implicit schema creation to API or worker startup.
   - Keep downgrade behavior reversible and remove the index/column in a SQLite-compatible way.

3. **Run migration and backend regression checks.**
   - Agent: implementer
   - Run the focused migration test against a fresh temporary SQLite file and the full backend test suite.
   - Confirm the existing migration-backed test fixture still initializes and the rest of the vertical-slice tests pass.

## Acceptance checks

- `cd backend; uv run pytest -q tests/test_vertical_slice.py -k initial_alembic_revision` passes.
- A fresh temporary SQLite database accepts `uv run alembic upgrade head` and reports `product_photos.draft_id`, its foreign key to `product_drafts.id` with `SET NULL`, and `ix_product_photos_draft_id`.
- `cd backend; uv run pytest` passes.
- The migration remains Alembic-managed; API and worker startup do not call `create_all`.
- Product catalog scope and the GENERIC/DEMO-only MISA export claim remain unchanged.

## Files in scope

- `backend/alembic/versions/0001_initial.py`
- `backend/tests/test_vertical_slice.py` or a focused migration test module
- `backend/tests/conftest.py` only if needed to isolate the migration test database

## Constraints

- Preserve SQLite WAL and explicit Alembic migrations.
- Preserve foreign-key delete behavior and the draft-photo index.
- Do not expand this task to unrelated verifier findings or domain changes.
