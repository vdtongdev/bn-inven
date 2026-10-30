# Plan: Nemotron empty-content response

**Agent:** implementer  
**Status:** implemented and verified with fake transports and one synthetic-label smoke run.

## Goal

Prevent HTTP 200 responses with missing model content from becoming ambiguous extraction failures, while keeping the product extraction contract strict and the provider output subject to human review. The selected Nemotron model remains test-only; no extraction accuracy is claimed.

## Current evidence

- One live OpenRouter call using a synthetic label reproduced HTTP 200 with a `choices[0].message` object whose `content` was `null`. The adapter rejected the response as invalid and the worker marked the job failed after one attempt.
- The request set `max_tokens=700` and did not set a reasoning parameter. No business photo, API key, or raw model output was logged.
- OpenRouter's [Nemotron model page](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free) says reasoning is enabled by default and can be disabled. Its [reasoning token guide](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) says reasoning tokens count against `max_tokens`; if they exhaust the budget, a response may have `finish_reason: length` and empty content.
- Reasoning-budget exhaustion is a plausible explanation, not a confirmed cause: the first live response's `finish_reason` and usage details were not retained.

## Ordered tasks

1. **Run and preserve the null-content regression test first.**
   - Keep the existing test in `backend/tests/test_openrouter_provider.py` that simulates HTTP 200 with null content.
   - Run `cd backend; uv run pytest tests/test_openrouter_provider.py` against the current implementation and record the observed failure before changing production code. Extend the request assertion to require reasoning disabled if this fits the existing test structure.

2. **Bound the request and handle empty content explicitly.**
   - In the OpenRouter adapter, send `reasoning: {"enabled": false}` for this bounded structured catalog extraction request.
   - Return a distinct sanitized permanent error for HTTP 200 responses whose content is null, non-string, or empty. Keep JSON decoding and `ExtractionPayload` validation strict; do not inspect, parse, or treat model reasoning as product data.
   - Preserve secret/raw-response redaction and the current no-business-photo logging behavior. Do not change approval, draft, or export rules.

3. **Verify offline first, then one synthetic live request.**
   - Run the focused provider tests, then the full backend suite with the mock provider and fake HTTP transport; no paid call is needed for these checks.
   - After those pass, make one live smoke request using only the synthetic test label. Confirm the worker completes and creates a reviewable pending draft. Do not print the API key, raw response, or reasoning content; report only sanitized status and whether a draft was created.
   - Do not make repeated live calls to tune the prompt. If the smoke request still returns empty content, retain the safe failure behavior and report the sanitized response metadata needed for diagnosis, if available.

4. **Independent verification.**
   - Have the verifier run the focused test and full backend suite, inspect the request setting/error handling, and repeat the single synthetic smoke check only if necessary and explicitly authorized. Keep test photos synthetic and avoid secrets in logs or reports.

## Acceptance checks

- The regression test fails against the old behavior and passes after the request disables reasoning and empty content maps to a distinct sanitized permanent error.
- Tests cover null, empty, non-string, malformed JSON, valid schema content, request reasoning configuration, and secret/raw-content redaction.
- `cd backend; uv run pytest tests/test_openrouter_provider.py` and `cd backend; uv run pytest` pass without live API calls.
- One separately identified synthetic live smoke request produces a persisted, reviewable pending draft, or reports a sanitized permanent failure. It does not approve a catalog item or generate MISA rows.
- The hypothesis about reasoning-budget exhaustion remains labeled unconfirmed unless a later response safely captures sufficient `finish_reason`/usage metadata to establish it.

## Implementation outcome (2026-10-29)

- Added `reasoning: {"enabled": false}` to the OpenRouter request. The adapter now raises a distinct sanitized permanent `ProviderEmptyContentError` when `message.content` is null, non-string, empty, or whitespace-only; it never reads model reasoning as extraction data.
- Confirmed regression-first behavior: the null-content test failed before the change because the adapter returned its generic invalid-response message. After the change, focused provider tests passed (13 passed) and the full backend suite passed (26 passed).
- Ran one app/API/worker smoke job with only the generated synthetic label and an isolated temporary SQLite database. Outcome: job `Succeeded`, one attempt, a draft was created with `Pending` review status. No raw extraction text, key, headers, or reasoning were printed.
- The original cause of the null content remains a hypothesis. Disabling reasoning was applied as a bounded request control; no accuracy or production-readiness claim is made for the selected model.

## Limits

- The candidate model is not validated for catalog extraction accuracy or production readiness.
- No business photo, API credential, raw response, or reasoning content belongs in logs, test fixtures, or documentation.
