# Domain model

| Entity | Role and relationships |
| --- | --- |
| `CaptureBatch` | Groups a capture session; owns photos and drafts. Deletion cascades to capture work. |
| `ProductPhoto` | Private source file metadata, dimensions, MIME, byte size and SHA-256; belongs to one batch. |
| `ExtractionJob` | Durable job for one photo; queued/running/succeeded/failed state, attempt count and error. |
| `ExtractionResult` | Unique result per job; associates photo, schema/prompt version, provider/model, raw response, observed facts and suggestions. |
| `ProductDraft` | Editable review record, unique BN-generated item code, extracted fields, status and optional catalog match. Batch barcode duplicates are constrained. |
| `DraftAuditEvent` | Human edit, approval or exclusion for one draft; stores a UTC time and only changed-field before/after values. Draft deletion cascades to its events. |
| `CatalogItem` | Approved normalized catalog record. No quantity fields. Item code is distinct from barcode and manufacturer model. |
| `MisaExportProfile` | Worksheet, start row, field-to-column mapping, required fields, allowed values. Demo flag is explicit. |
| `ExportRun` | Profile, output location, item count, status and immutable values snapshot. Profile deletion is restricted. |

Relationships use cascade for batch-owned capture data, `SET NULL` for historical optional catalog matching/extraction links, and restrict profile deletion after export. Searchable item code, names, barcode, model and workflow state have indexes. JSON is reserved for original AI output, profile configuration and the export snapshot.

Draft audit history is a separate append-only event relation indexed by draft and creation time. It records changed field values and review-status transitions without staff identity (the application has shared authentication). The history API returns events chronologically and excludes photos and extraction/provider traces. The event rows cascade when the draft or its owning batch is deleted.

## Approval requirements

A draft is not a catalog item until a human approves it. Product name, business item type and primary unit are required. Category is optional classification. Package size is descriptive packaging, not stock quantity. A review status of `NeedsCorrection` is set after edits; `Excluded` is available. The original extraction remains attached separately from the editable draft.
