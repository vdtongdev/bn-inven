# Architecture

## Purpose and scope

BN-Inven turns label/product photos into human-reviewed catalog records suitable for later import into an accounting catalog. It does not manage quantities, warehouses, purchase orders, or stock movements. Correctness and traceability take priority over automatic completion.

## Stack and boundaries

- `frontend/`: React, Vite, TypeScript, Tailwind and `vite-plugin-pwa`; API calls live in `src/api.ts`, while the screen currently composes the simple workflow.
- `backend/app/api`: API routes are currently in `main.py`; schemas are Pydantic models in `schemas.py`.
- `backend/app/models.py`: SQLAlchemy relational entities with searchable columns and JSON only for raw extraction/profile/snapshot payloads.
- `backend/app/services.py`: upload validation, normalization and approval rules.
- `backend/app/ai/`: provider adapters, versioned prompts and strict extraction payload. Mock is default; optional `openrouter` uses a fixed backend endpoint and an environment-only API key. The worker preprocesses an inference copy while retaining the original upload.
- `backend/app/workers/`: a separate durable database worker reads persisted jobs and writes extraction plus draft atomically.
- `backend/app/exporters/`: profile-driven workbook generation, separate from extraction logic.
- `backend/alembic/`: explicit database schema migration entry point. API and worker startup never create or alter tables; run Alembic before starting either process.

## Workflow

1. Create a capture batch and upload one or more JPEG/PNG/WebP product photos.
2. The API checks content type, byte limit, decodability and pixel dimensions, assigns a random server filename, stores the source image privately, and commits a queued job.
3. The worker validates the provider response against `ExtractionPayload`, stores the original provider response (including any usage/cost metadata), model and prompt versions, then creates a pending draft. The OpenRouter adapter sends a bounded EXIF-corrected JPEG inference copy; the original upload remains unchanged. Mock mode returns null fields rather than inventing label facts. Permanent credential/request/schema failures stop immediately; transient network, rate-limit and provider failures use the bounded durable job retry policy.
4. Staff fill required values and approve. Approval requires product name, business item type and primary unit; it creates the application-managed catalog item code record. AI cannot approve.
5. Export selects approved drafts and snapshots their values through a separately configured profile into XLSX.

Job states are queued, running, succeeded and failed with a bounded attempt count. SQLite and worker share a volume. Run one worker process for the MVP. Exact barcode hits, followed by exact manufacturer/model hits, against an approved catalog item or another draft in the same batch are saved as duplicate suggestions with the candidate item code. They do not merge records or approve drafts. The initial retry delay and lease behavior need additional hardening before running multiple worker replicas.

## PWA behavior

The app can be installed and caches its application shell. It reports browser connectivity. Initial release requires a connection for API calls and recognition; there is no reliable offline upload queue, and no promise of background upload after the PWA closes. Camera capture uses a browser file input with `capture="environment"`, with a regular file picker fallback.

## Decisions and limits

- SQLite WAL suits one small always-on host and a single worker; retain portable SQLAlchemy/Alembic boundaries for a later PostgreSQL migration.
- OpenRouter is an optional vision provider behind the adapter boundary. `AI_PROVIDER=mock` remains the default. `nvidia/nemotron-3.5-super-vl:free` is a temporary, unvalidated test model selection, not an accuracy or production claim. Provider usage in the response is trace metadata, not a verified bill or cost estimate.
- No exact MISA product/template is selected. The app emits only its generic demo workbook, never a claimed AMIS or SME workbook.
- Access protection is expected at the HTTPS reverse proxy. If the PWA is hosted separately on Cloudflare Pages, use Cloudflare Access or an equivalent authenticated gateway that protects API calls too; do not embed a shared secret in public JavaScript.
