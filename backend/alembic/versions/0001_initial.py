"""Create the initial BN-Inven catalog schema explicitly."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_code", sa.String(48), nullable=False),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("brand", sa.String(160)),
        sa.Column("model_number", sa.String(120)),
        sa.Column("barcode", sa.String(80)),
        sa.Column("item_type", sa.String(40), nullable=False),
        sa.Column("category_code", sa.String(80)),
        sa.Column("primary_unit", sa.String(40), nullable=False),
        sa.Column("package_size", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "misa_export_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("worksheet_name", sa.String(31), nullable=False),
        sa.Column("start_row", sa.Integer(), nullable=False),
        sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("required_fields", sa.JSON(), nullable=False),
        sa.Column("permitted_values", sa.JSON(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "product_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("capture_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_photos_batch_id", "product_photos", ["batch_id"])
    op.create_index("ix_product_photos_sha256", "product_photos", ["sha256"])
    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("photo_id", sa.String(36), sa.ForeignKey("product_photos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("queued", "running", "succeeded", "failed", name="jobstatus"), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extraction_jobs_photo_id", "extraction_jobs", ["photo_id"])
    op.create_index("ix_extraction_jobs_status", "extraction_jobs", ["status"])
    op.create_index("ix_job_claim", "extraction_jobs", ["status", "next_attempt_at"])
    op.create_table(
        "extraction_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("photo_id", sa.String(36), sa.ForeignKey("product_photos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=False),
        sa.Column("observed", sa.JSON(), nullable=False),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extraction_results_photo_id", "extraction_results", ["photo_id"])
    op.create_table(
        "product_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("capture_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_result_id", sa.String(36), sa.ForeignKey("extraction_results.id", ondelete="SET NULL"), unique=True),
        sa.Column("item_code", sa.String(48), nullable=False),
        sa.Column("product_name", sa.String(240)),
        sa.Column("brand", sa.String(160)),
        sa.Column("model_number", sa.String(120)),
        sa.Column("barcode", sa.String(80)),
        sa.Column("item_type", sa.String(40)),
        sa.Column("category_code", sa.String(80)),
        sa.Column("primary_unit", sa.String(40)),
        sa.Column("package_size", sa.String(120)),
        sa.Column("review_status", sa.Enum("pending", "needs_correction", "approved", "excluded", name="reviewstatus"), nullable=False),
        sa.Column("matched_catalog_item_id", sa.String(36), sa.ForeignKey("catalog_items.id", ondelete="SET NULL")),
        sa.Column("duplicate_suggestion", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_drafts_batch_id", "product_drafts", ["batch_id"])
    op.create_index("ix_product_drafts_item_code", "product_drafts", ["item_code"], unique=True)
    op.create_index("ix_product_drafts_product_name", "product_drafts", ["product_name"])
    op.create_index("ix_product_drafts_model_number", "product_drafts", ["model_number"])
    op.create_index("ix_product_drafts_barcode", "product_drafts", ["barcode"])
    op.create_index("ix_product_drafts_review_status", "product_drafts", ["review_status"])
    with op.batch_alter_table("product_photos", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "draft_id",
                sa.String(36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_product_photos_draft_id_product_drafts",
            "product_drafts",
            ["draft_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_product_photos_draft_id", "product_photos", ["draft_id"])
    op.create_index("ix_catalog_items_item_code", "catalog_items", ["item_code"], unique=True)
    op.create_index("ix_catalog_items_product_name", "catalog_items", ["product_name"])
    op.create_index("ix_catalog_items_model_number", "catalog_items", ["model_number"])
    op.create_index("ix_catalog_items_barcode", "catalog_items", ["barcode"])
    op.create_table(
        "export_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("misa_export_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("export_runs")
    op.drop_index("ix_catalog_items_barcode", table_name="catalog_items")
    op.drop_index("ix_catalog_items_model_number", table_name="catalog_items")
    op.drop_index("ix_catalog_items_product_name", table_name="catalog_items")
    op.drop_index("ix_catalog_items_item_code", table_name="catalog_items")
    op.drop_index("ix_product_photos_draft_id", table_name="product_photos")
    with op.batch_alter_table("product_photos", recreate="always") as batch_op:
        batch_op.drop_column("draft_id")
    op.drop_index("ix_product_drafts_review_status", table_name="product_drafts")
    op.drop_index("ix_product_drafts_barcode", table_name="product_drafts")
    op.drop_index("ix_product_drafts_model_number", table_name="product_drafts")
    op.drop_index("ix_product_drafts_product_name", table_name="product_drafts")
    op.drop_index("ix_product_drafts_item_code", table_name="product_drafts")
    op.drop_index("ix_product_drafts_batch_id", table_name="product_drafts")
    op.drop_table("product_drafts")
    op.drop_index("ix_extraction_results_photo_id", table_name="extraction_results")
    op.drop_table("extraction_results")
    op.drop_index("ix_job_claim", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_status", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_photo_id", table_name="extraction_jobs")
    op.drop_table("extraction_jobs")
    op.drop_index("ix_product_photos_sha256", table_name="product_photos")
    op.drop_index("ix_product_photos_batch_id", table_name="product_photos")
    op.drop_table("product_photos")
    op.drop_index("ix_catalog_items_barcode", table_name="catalog_items")
    op.drop_index("ix_catalog_items_model_number", table_name="catalog_items")
    op.drop_index("ix_catalog_items_product_name", table_name="catalog_items")
    op.drop_index("ix_catalog_items_item_code", table_name="catalog_items")
    op.drop_table("misa_export_profiles")
    op.drop_table("catalog_items")
    op.drop_table("capture_batches")
