# AI text normalization

New extraction results use Unicode sentence case for product name, generic type,
brand, and sales unit. The worker normalizes suggestions before persisting them;
raw provider evidence and human edits remain unchanged. Category codes, barcode,
model number, package measurements, arbitrary attributes and confidence retain
their original semantics and case. Existing records are not rewritten.
Recognized case-sensitive measurement symbols in sales units also retain case.

Vietnamese product names, types and units are requested explicitly in the
versioned provider prompt. A bounded list of unambiguous English package-unit
aliases is canonicalized locally; it is not a general translation engine.
Uncertain translations remain null rather than invented.

1. Agent: implementer. Add regression tests for Unicode sentence case, nulls,
   Vietnamese units, raw evidence, identifier/measurement preservation and worker
   integration. Run the new tests before implementation to verify failure.
2. Agent: implementer. Add shared AI payload normalization at the worker boundary
   and update/version the Vietnamese extraction prompt. Keep the approval flow.
3. Agent: verifier. Review the diff and run focused and backend tests. Report
   pre-existing failures separately. No live paid model call, commit or push.
