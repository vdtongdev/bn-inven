# Plan: Resolve Phase 1 verifier findings

## Goal

Resolve the four findings from the independent Phase 1 review while preserving BN-Inven's product-catalog scope, the human-review boundary, and the GENERIC/DEMO-only export claim.

## Tasks

1. **Keep and sharpen the regression checks.** Retain `backend/tests/test_verifier_regressions.py` as the first task. Ensure it checks that no unauthenticated public route bypasses Caddy, API and worker startup do not create schema, duplicate barcodes remain reviewable, and the frontend does not read or bundle a shared access token. Run the dependency-free check before fixes to confirm each finding reproduces.

2. **Close the public access bypass and define the access boundary.** Update `docker-compose.yml` and `infra/Caddyfile` so application traffic enters through the protected Caddy route; do not publish an unprotected frontend or API port. Keep the API on the internal Compose network. Document how access protection works when static assets are hosted on Cloudflare Pages, where Caddy does not protect the page origin.

3. **Make Alembic the only schema-management path.** Remove `create_all` initialization from API and worker startup in `backend/app/main.py`, `backend/app/db.py`, and `backend/app/workers/extraction.py`. Replace `create_all`/`drop_all` in `backend/alembic/versions/0001_initial.py` with explicit Alembic operations. Document the explicit `alembic upgrade head` deployment step. Add or update tests proving process startup does not create the schema and the migration creates the expected tables.

4. **Treat duplicate barcodes as review suggestions.** Remove or revise the draft uniqueness constraint in `backend/app/models.py` so a repeated extracted barcode cannot fail a durable job. Add exact-barcode matching in the extraction/business service and return a duplicate suggestion for human review. Do not auto-approve, merge catalog records, or let AI write final export rows. Cover repeated barcodes within a batch and against the catalog in backend tests.

5. **Remove shared credentials from the browser bundle.** Remove `VITE_APP_ACCESS_TOKEN` use from `frontend/src/api.ts` and `frontend/src/App.tsx`. Rely on the documented server-side access boundary; do not replace it with another build-time secret. Add a source/config check that rejects shared secrets in frontend build inputs.

6. **Verify the complete change and update operational docs.** Update `.env.example`, `README.md`, and `docs/deployment.md` to match the chosen access and migration workflow. Keep the MISA target explicitly unknown and the exporter labeled GENERIC/DEMO. Run the checks below, then have an independent verifier review the complete diff.

## Acceptance checks

- `python backend/tests/test_verifier_regressions.py` passes and covers all four original findings.
- `cd backend; uv run pytest` passes, including migration, duplicate matching, job behavior, approval, and export tests.
- `cd frontend; npm test` and `npm run build` pass; no shared access token appears in frontend source or generated assets.
- Compose configuration has no direct public frontend/API bypass; protected requests pass only through the configured access boundary.
- `cd backend; uv run alembic upgrade head` creates the database schema. API and worker startup do not create tables implicitly.
- Documentation explains the Cloudflare Pages access boundary and the explicit production migration command.
- GENERIC/DEMO export disclaimer remains; no MISA AMIS/SME compatibility claim is added.

## Constraints and assumptions

- Keep SQLite WAL and the shared persistent database volume for API and worker.
- Keep application behavior and secrets server-side; no shared secret is embedded in Vite assets.
- Network package installation and Docker may remain unavailable in the current environment. If so, report those checks as unverified and run dependency-free checks without claiming full validation.
