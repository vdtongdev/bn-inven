"""Store editable product type and the composed draft name.

Existing approved names stay aligned with their immutable catalog entries.
"""

import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "0003_product_final_name"
down_revision = "0002_product_draft_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_drafts", sa.Column("product_type", sa.String(160), nullable=True))
    op.add_column("product_drafts", sa.Column("final_name", sa.String(800), nullable=True))
    connection = op.get_bind()
    drafts = sa.table("product_drafts", sa.column("id"), sa.column("product_name"),
                      sa.column("product_type"), sa.column("final_name"), sa.column("brand"),
                      sa.column("primary_unit"), sa.column("package_size"),
                      sa.column("extraction_result_id"), sa.column("review_status"))
    results = sa.table("extraction_results", sa.column("id"), sa.column("observed", sa.JSON))
    rows = connection.execute(sa.select(drafts, results.c.observed).select_from(
        drafts.outerjoin(results, drafts.c.extraction_result_id == results.c.id))).mappings().all()
    for row in rows:
        product_type = (row["observed"] or {}).get("product_type")
        parts = [" ".join((value or "").split()) for value in
                 (product_type, row["brand"], row["product_name"], row["primary_unit"], row["package_size"])]
        identity = lambda value: unicodedata.normalize("NFC", value).lower()
        if parts[2] and identity(parts[2]) in {identity(parts[0]), identity(parts[1])}:
            parts[2] = ""
        final_name = " ".join(part for part in parts if part) if any(parts[:3]) else None
        if row["review_status"] == "approved":
            final_name = row["product_name"]
        connection.execute(drafts.update().where(drafts.c.id == row["id"]).values(
            product_type=product_type, final_name=final_name))


def downgrade() -> None:
    op.drop_column("product_drafts", "final_name")
    op.drop_column("product_drafts", "product_type")
