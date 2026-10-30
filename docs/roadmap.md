# MVP milestones

## Phase 1 foundation (current)
- Capture batches, upload validation and private source image storage.
- Durable database job + deterministic no-cost mock provider.
- Traceable extraction result, editable drafts and approval validation.
- GENERIC/DEMO XLSX export with per-run snapshot.
- Responsive installable PWA shell and Docker/Caddy baseline.
- ProductDraft edit, approval and exclusion audit history with a narrow chronological endpoint.

## Completed architecture work

- OpenRouter vision provider adapter and provider abstraction. `AI_PROVIDER=mock` remains the no-cost default; the current `nvidia/nemotron-3.5-super-vl:free` selection is a temporary, unvalidated test candidate, not an accuracy or production claim.
- ProductDraft correction and review audit events are persisted atomically with draft/catalog mutations. No actor identity is recorded.

## Next
1. Select the MISA product and obtain its official template; this remains user-blocked. Implement its export profile and verify by trial import with sample catalog records before claiming compatibility.
2. Evaluate the temporary vision model with an authorized labeled set before selecting a production model or claiming extraction accuracy.
3. Improve duplicate matching, worker lease/backoff, authentication and operational telemetry.
4. Add PostgreSQL migration when multiple writers, concurrency, or recovery requirements justify it.

## Postponed

Offline AI, background upload while the PWA is closed, stock/warehouse workflows, multi-tenant SaaS, distributed queues, advanced visual design, and automatic MISA template discovery.
