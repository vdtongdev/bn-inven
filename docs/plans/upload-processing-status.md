# Upload processing status fix

## Objective

Ensure every accepted image upload is connected to a reviewable product or reports an accurate non-success state. Keep BN-Inven a product catalog: do not add inventory quantities or bypass human approval.

## Diagnosis

The worker saves an extraction for an additional photo but only links it when the photo has no existing draft, then marks the job `Succeeded`. The job lookup consequently returns no `draft_id`, and the visible product continues to show the first photo's extraction. Separately, SHA-based deduplication may reuse a successful job tied to an excluded draft; the UI filters that draft out while still displaying success.

The focused regression tests are already present in `backend/tests/test_upload_processing.py` and currently fail for both cases. Task 1 retains these tests and verifies the failures before the fix.

## Implementation sequence

1. **Keep and run the regression tests.** Preserve both tests in `backend/tests/test_upload_processing.py`. Confirm each fails on the base behavior and record the failing assertions.
2. **Link additional-photo extraction results.** Update the worker and job/draft lookup as needed so a completed additional-photo extraction is associated with its existing draft and returned with the correct `draft_id`. Preserve extracted values as suggestions subject to the existing review flow.
3. **Handle deduplication after exclusion.** Change upload deduplication so a previous successful job attached to an excluded draft cannot make a new upload appear successfully processed with no visible review product. Reuse or create a reviewable draft according to the existing catalog and dedup model; keep the new job's status and response consistent with the visible result.
4. **Verify the change.** Run the focused regression tests, the backend suite, and the frontend checks. Review the diff for schema/migration needs; if any are required, add an explicit migration and test it rather than relying on startup migration.

## Acceptance

- `cd backend; uv run pytest tests/test_upload_processing.py -q` passes both regression tests.
- `cd backend; uv run pytest` passes.
- `cd frontend; npm test` and `npm run build` pass.
- Successful jobs for these upload paths identify a visible review product; excluded products remain excluded unless the existing review behavior explicitly reopens them.
- No AI result becomes final without human review, and no stock or on-hand quantity behavior is introduced.

## Risks and constraints

- A draft currently appears to expose one extraction. Linking multiple photo results may require a small model/API adjustment; avoid discarding existing extraction evidence or adding a schema change without an Alembic migration.
- Deduplicated photos must not inherit an excluded review outcome in a way that hides the new upload while reporting success.
- Keep MISA/export behavior and the demo export disclaimer unchanged.
