# Preserve edits during catalog refresh

Root cause: `refreshBatches` replaces the same draft state that text inputs edit every 2.5 seconds, discarding unsaved changes.

1. Agent: implementer. Keep the failing `frontend/src/input-editing.test.tsx` regression covering typed text and explicitly cleared text across polling.
2. Agent: implementer. Track unsaved fields separately from server drafts; merge edits for display/save/approval while allowing fresh server fields and new drafts to arrive. Retain edits on failed saves, clear only successfully saved values, and preserve newer edits made during a save. Prevent stale in-flight refresh responses from reverting a successful save. Add focused regression cases for these boundaries.
3. Agent: verifier. Confirm regression fails on base implementation and passes after the fix; run frontend suite and production build. Identify pre-existing failures separately without changing tests solely to make them pass.

No backend or schema changes. Do not change approval gates or export behavior.
