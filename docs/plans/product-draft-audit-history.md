# Plan: Product draft audit history

**Agent:** implementer  
**Status:** implemented and verified; audit events are persisted and exposed by the API.

## Goal

Persist human edits and review-status transitions for `ProductDraft` so staff can see how a draft changed from its original AI extraction. Keep catalog creation, approval validation, item codes, export mappings, and workbook behavior unchanged. MISA product/template selection remains blocked on user input; this work is independent.

## Ordered tasks

1. **Add regression tests first.**
   - In a focused audit-history test module, cover a real field edit, approval, exclusion, a no-op patch, chronological retrieval, unknown draft, and history deletion with its owning draft/batch.
   - Assert edits contain only actual before/after deltas; review transitions include old/new status; no-op requests add no event. Assert approval still creates exactly the existing catalog item and only after validation.
   - Assert `GET /api/drafts/{id}/history` does not expose raw AI/provider response, credentials, or other extraction trace content. Run the focused tests against current code and record expected failures before implementation.

2. **Add the audit association model and explicit migration.**
   - Add `DraftAuditEvent` in `backend/app/models.py` with a primary key, required `draft_id` FK to `product_drafts.id` using `ON DELETE CASCADE`, event/action type (`edited`, `approved`, `excluded`), UTC timestamp, and JSON field-level changes containing before/after values. Index `(draft_id, created_at)` for ordered history reads.
   - Add a ProductDraft relationship with ORM delete-orphan behavior consistent with the database FK. Do not add an actor/user field: the app has shared Basic Auth and no authenticated staff identity.
   - Create a new Alembic migration with explicit create-table/index operations and a reversible downgrade. Do not modify the initial migration or introduce runtime `create_all` schema changes.

3. **Record events atomically with human mutations.**
   - Refactor the draft mutation path in `backend/app/main.py` and, if helpful, a small service so edits, approval, and exclusion add audit events in the same database transaction as their existing draft/catalog mutation.
   - Compute deltas after applying the existing normalization and review rules. Record only changed values and status transitions; no effective no-op means no event. A status transition caused by current PATCH behavior is an actual transition and must be captured.
   - Keep approval validation and CatalogItem creation semantics intact. AI extraction creation is not a human audit event; the original AI result remains linked through `extraction_result_id`.

4. **Expose a narrow chronological history endpoint.**
   - Add `GET /api/drafts/{draft_id}/history`, returning event ID, action, timestamp, and changed-field before/after values in chronological order with stable tie-breaking.
   - Return 404 for a missing draft. Do not embed extraction payloads, raw provider responses, photos, secrets, or catalog/export snapshots in this response.

5. **Run migration and behavior checks; update domain docs.**
   - Run the focused audit tests, a fresh temporary SQLite Alembic upgrade that verifies the audit table, FK cascade and index, then the full backend suite. Include migration downgrade/re-upgrade coverage where the existing migration test setup supports it.
   - Update `docs/domain-model.md` with the audit relationship, event contents and delete behavior; update `docs/roadmap.md` to mark provider choice/adapter complete and identify this audit work as the next independent engineering item. Keep MISA selection listed as user-blocked. No live OpenRouter calls or secret access are needed.

## Acceptance checks

- `cd backend; uv run pytest tests/test_draft_audit.py` passes; `cd backend; uv run pytest` passes.
- A fresh SQLite Alembic upgrade creates the event table, `(draft_id, created_at)` index and cascading FK; downgrade and re-upgrade work without implicit schema creation.
- Field edits, approval, and exclusion each create a durable event with accurate deltas in the same transaction as the mutation. A failed transaction leaves neither a partial draft change nor a partial event.
- No-op patches create no event. Approval continues to create exactly one existing CatalogItem, and invalid drafts remain unapproved.
- History is chronological, returns 404 for unknown drafts, and contains no raw AI/provider response. Deleting a draft or owning batch removes its audit events through cascade.
- No user identity is asserted, and no stock quantity, ItemCode, catalog/export behavior, or MISA compatibility claim changes.

## Files likely in scope

- `backend/app/models.py`, `backend/app/main.py` and optionally a focused draft-audit service/schema
- New `backend/alembic/versions/` migration
- New focused tests under `backend/tests/`
- `docs/domain-model.md` and `docs/roadmap.md`

## Limits

- This is correction/review history, not a general security log or staff attribution system.
- The original AI result remains separately traceable; the history endpoint must not return its raw response.
- No change is made to generic/demo MISA export behavior or the unresolved need to select an official MISA template and trial-import it.

## Implementation outcome (2026-10-30)

- Added `DraftAuditEvent` with draft ownership, an action constraint, UTC timestamp, JSON before/after deltas, a `(draft_id, created_at)` index and cascading deletion. Added reversible Alembic revision `0002_product_draft_audit`.
- PATCH edits/exclusions and approvals now write field deltas in the same transaction as the existing mutation. No-op patches create no event. Approval validation and catalog creation remain unchanged; failed approval commit test confirms neither catalog item, approval status nor audit event is partially persisted.
- Added `GET /api/drafts/{id}/history`, ordered by creation time then event ID, with a narrow response schema that excludes extraction/provider traces.
- Regression-first focused run before implementation: 4 tests failed as expected due to absent history route/table/schema. Final focused command `uv run --extra dev pytest tests/test_draft_audit.py --basetemp .pytest-tmp-audit-final-focused -q` passed (5 passed). The migration test exercised fresh upgrade, downgrade to `0001_initial`, and re-upgrade, verifying the index and cascading FK.
- Final full backend command `uv run --extra dev pytest --basetemp .pytest-tmp-audit-final-full -q` passed (31 passed, 6 dependency/config deprecation warnings).
- Updated `docs/domain-model.md` and `docs/roadmap.md`. OpenRouter adapter work is marked complete; the Nemotron model stays an unvalidated test candidate, and official MISA selection remains user-blocked.
