# UI catalog review adjustments

## Goal

Simplify the product review form, show when image recognition is running, and guide extraction to compose product names in the order `product type + brand + package size` (for example, `Bột bánh pancake Fancy bịch 1 kg`).

## Scope

- Remove model/manufacturer number, barcode, and product type from the draft review form. Keep these fields in backend data and export behavior.
- After photo upload, show a visible loading indicator while its existing extraction job is queued or running. Stop the indicator on success or failure and surface failures through the existing status message.
- Update the extraction prompt to compose the product name from only clearly readable product type, brand, and package size. Preserve nullable/uncertain extraction behavior and keep the separate brand and package-size values.
- Hide batch naming, creation, switching, and history UI. Combine drafts from all existing batches into one review list. Keep using the latest existing batch for uploads, or silently create a default internal batch if none exists; leave the batch API and data model unchanged.

## Tasks

1. Update `frontend/src/App.tsx` to remove the three review fields and poll the existing `/api/jobs/{job_id}` endpoint for the upload's terminal state; render an accessible processing indicator during queued/running states.
   Agent: implementer
2. Update `backend/app/ai/prompts.py` to state the product-name ordering and examples while preserving the instruction to use only visible facts.
   Agent: implementer
3. Update `frontend/src/App.tsx` to remove batch controls and render drafts from all batches together while retaining an internal upload batch.
   Agent: implementer
4. Review the diff against this plan and inspect the affected frontend and prompt flows. Do not add or run tests unless requested.
   Agent: verifier

## Acceptance

- The review form presents product name, brand, unit, and package size; it does not present model/manufacturer number, barcode, product type, or suggested category.
- An uploaded photo displays a loading indicator for queued/running extraction and clears it after a terminal status.
- Prompt guidance requests names in product type, brand, package size order and does not invite guesses when any component is uncertain.
- Backend identifier fields, approval flow, and export mappings are not removed or altered.
- Batch controls and batch names are hidden; all existing drafts appear in one combined review list, and uploads continue through an internal batch.

## Follow-up request

- Remove the `category_code` / “Nhóm hàng gợi ý” field from the review UI. Keep category data in the existing API/save/export flow.
- The user approved hiding the batch workflow and showing one combined list. Retain the internal batch association required by the upload API; do not change backend batch APIs or schema.

## Follow-up request: item removal and composed title

- Add a remove action for unapproved drafts using the existing `review_status = Excluded` patch behavior. Hide excluded drafts from the combined list. This is a soft exclusion, not hard deletion; do not change approved catalog or export records.
- Extract `product_type` as a nullable field and retain it in the existing `ExtractionResult.observed` JSON. Keep business `item_type` (goods/service) distinct. Do not add a database column or migration.
- Compose the visible item title from product type, optional manufacturer/brand, product name, primary unit, and amount/package size. If normalized product name equals normalized product type, show the type once and include manufacturer/brand; otherwise include manufacturer/brand when available.
- Request Vietnamese product type and unit values. Preserve proper names and brands, and return null for uncertain values.
- For existing drafts without `product_type`, fall back to their current `product_name` title.

## Follow-up bug report: stale Vite development module

### Diagnosis

- The remove-button source contains `bg-red-50`, but the live `/src/App.tsx` module did not. The regression test `frontend/src/live-dev-server.test.ts` reproduced this mismatch.
- The likely cause is that the WSL Vite watcher missed edits made to the Windows-mounted `/mnt/c` workspace. The running server must be restarted after changing Vite configuration.

### Fix plan

1. Keep the failing regression test added during diagnosis.
   Agent: implementer
2. Configure Vite to watch the mounted workspace reliably with polling and a bounded interval; keep the change scoped to the development server.
   Agent: implementer
3. Restart the Vite development server, verify the targeted regression test passes, and confirm the live `/src/App.tsx` response contains the red remove-button classes.
   Agent: verifier

### Acceptance

- The regression test passes against the active development server.
- The live transformed module includes `bg-red-50` and the remove-button text.
- No PWA cache, backend, API, or product behavior changes are made for this watcher issue.
