# Plan: OpenRouter vision adapter

**Agent:** implementer  
**Status:** implemented and verified with fake HTTP transport; no provider call has been made.

## Goal

Add an OpenRouter adapter behind the existing synchronous `VisionProvider` interface. Keep mock extraction as the default, preserve the original photo, validate every model response with `ExtractionPayload`, and keep API credentials on the backend. The configurable model selection is `nvidia/nemotron-3.5-super-vl:free`, a temporary unvalidated test candidate with no accuracy or production claim.

## Ordered tasks

1. **Add adapter contract tests using a fake HTTP transport.**
   - Cover a successful chat-completions response with image content and valid extraction JSON; null uncertain fields; malformed JSON, extra fields and invalid values; HTTP errors, timeouts and sanitized error text.
   - Assert the adapter sends a Bearer credential only to the backend endpoint, uses the configured model and versioned prompt, includes the image as a base64 data URL, and does not put the key in the result, logs or raised errors. Tests must make no real OpenRouter requests.
   - Verify mock mode remains the default and its existing extraction behavior is unchanged.

2. **Add backend configuration and the isolated prompt.**
   - Extend `backend/app/core/config.py` with a configurable model setting; keep the existing backend-only `AI_API_KEY` setting and `AI_PROVIDER=mock` default. Use the selected test candidate only as a configurable value, not as a claim of extraction quality.
   - Add `backend/app/ai/prompts.py` with a versioned prompt instructing the model to return only the extraction schema, use null for missing or uncertain facts, distinguish visible observations from category/unit suggestions, and never invent data.
   - Keep `.env.example` on mock mode and add only non-secret configuration. Do not include any user credential or key label in the example or documentation.

3. **Implement the OpenRouter adapter.**
   - Add `backend/app/ai/openrouter.py` and route `openrouter` through `backend/app/ai/providers.py`; unknown provider names must continue to fail closed. Use the fixed API origin `https://openrouter.ai/api/v1/chat/completions`, Bearer authentication, a configurable model, bounded connection/read timeouts, and a bounded output token limit. Do not add implicit HTTP retries; let the existing durable worker retry transient failures within its configured attempt limit.
   - Use Pillow to EXIF-transpose, resize to a bounded inference dimension, and re-encode an inference copy in memory. Never overwrite or replace the stored original photo.
   - Parse the returned message content as JSON and validate it with `ExtractionPayload` (`extra="forbid"`). Reject malformed or schema-invalid responses; never fill uncertain fields from guesses or send AI values directly to approved catalog records or export rows.
   - Capture provider/model/prompt version and the complete provider response, including returned usage/cost metadata, in the existing extraction trace. Avoid a migration unless the current JSON trace cannot retain required accounting metadata.
   - Classify permanent credential/request/schema failures separately from transient network, rate-limit and server failures so the worker does not repeatedly pay for requests that cannot succeed. Preserve bounded durable retries for transient errors, sanitize `last_error`, and never log request headers, credentials, or image data.

4. **Wire production dependency and environment handling.**
   - Move the pinned `httpx` dependency from dev-only to backend runtime dependencies because the worker will use it in production; regenerate `backend/uv.lock` through `uv` and keep versions pinned.
   - Keep credentials server-side in `AI_API_KEY`. For local configuration, first confirm root `.env` is absent before creating it; set the selected provider/model and user's supplied secret without printing or copying the secret into repository-tracked files. Treat `bn_inven` as the dashboard label only, not an API parameter. If `.env` already exists, preserve it and document the required settings instead of overwriting it.
   - Leave `.env.example`, tests, and CI on `AI_PROVIDER=mock`; the browser bundle must contain no OpenRouter credential.

5. **Verify traceability, failure behavior and documentation.**
   - Run backend tests with the fake transport and existing mock provider. Verify the worker persists raw response, provider/model/prompt metadata and usage; successful retries create one extraction/draft; permanent failures stop retrying; transient failures follow the existing bounded queue policy.
   - Update `docs/architecture.md` and `docs/deployment.md` to describe OpenRouter configuration, secret handling, inference-copy preprocessing, trace/usage storage, and that provider output remains a human-reviewed suggestion. Document the candidate model as unvalidated for catalog extraction and retain mock mode as the no-cost local/test path.

## Acceptance checks

- `cd backend; uv sync --extra dev; uv run pytest` passes with no real API credentials or network calls.
- Mock mode remains the default and the existing vertical-slice flow continues to pass.
- Fake-transport tests cover valid/null extraction, malformed/schema-invalid output, timeout/HTTP errors, secret redaction, trace metadata and worker retry classification.
- Original uploaded bytes remain unchanged; only the bounded inference copy is transformed.
- `.env.example` and frontend build artifacts contain no secret. No actual OpenRouter call is made as part of implementation verification.
- Optional live smoke test against the chosen model is a separate, usage-billed action and is not included in this plan's verification.

## Scope and limits

- No API key, key label, or secret value belongs in Git, docs, logs, test fixtures, API responses, or the frontend.
- No extraction accuracy, barcode readability, production readiness, or cost estimate is claimed without a separately authorized and reviewed live evaluation.
- Product approval remains a human action. Export profile mapping remains separate from AI extraction; MISA compatibility claims and catalog domain fields do not change.

## Reference documentation

- [OpenRouter developer documentation](https://openrouter.ai/developers)
- [OpenRouter image input tutorial](https://openrouter.ai/blog/tutorials/send-image-to-llm/)

## Implementation outcome (2026-10-29)

- Added versioned prompt `catalog-v2`, the fixed-endpoint OpenRouter adapter, strict extraction validation, and Pillow inference-copy preprocessing. Stored originals are not modified. Provider response JSON and returned usage/cost metadata remain in the existing extraction trace; no schema migration was needed.
- Worker permanent provider failures stop without retry. Transient provider failures use the existing bounded retry policy. Provider responses and exception bodies are not included in logs or `last_error`.
- Moved pinned `httpx==0.28.1` to runtime dependencies and regenerated `backend/uv.lock`. Added `AI_MODEL` to `.env.example`; mock remains the default.
- The root `.env` was absent. No API key value was available in this implementation task context, so no `.env` was created and no credential was guessed or copied. To enable the adapter, set `AI_PROVIDER=openrouter`, `AI_API_KEY`, and optionally `AI_MODEL` in the ignored root `.env`.
- Verification: `uv run --extra dev pytest --basetemp .pytest-tmp-openrouter` passed 21 tests; `uv lock --check --offline` and `uv run python -m compileall -q app tests` completed successfully. All adapter requests used `httpx.MockTransport`; no live API request was made.
- `nvidia/nemotron-3.5-super-vl:free` is the temporary test model selection and remains unvalidated for extraction accuracy. Returned usage/cost metadata is retained for traceability but is not a billing verification or cost estimate.
