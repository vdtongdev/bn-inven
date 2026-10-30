export type Batch = { id: string; name: string; created_at: string; photo_count: number; draft_count: number }
export type Draft = {
  id: string; batch_id: string; item_code: string; product_name: string | null; brand: string | null;
  model_number: string | null; barcode: string | null; item_type: string | null; category_code: string | null;
  primary_unit: string | null; package_size: string | null; review_status: string; photo_id: string | null; photo_ids: string[];
  duplicate_suggestion: { kind: string; scope: string; item_code: string; requires_human_review: boolean } | null;
  extraction: { provider: string; model: string; observed: Record<string, unknown>; suggestions: Record<string, unknown> } | null
}
export type ExportProfile = { id: string; code: string; name: string; is_demo: boolean }
