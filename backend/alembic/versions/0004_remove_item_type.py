"""Remove business item classification from the catalog and exporter profiles."""

from alembic import op
import sqlalchemy as sa

revision = "0004_remove_item_type"
down_revision = "0003_product_final_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Native DROP COLUMN keeps SQLite foreign keys and existing records intact.
    op.drop_column("product_drafts", "item_type")
    op.drop_column("catalog_items", "item_type")
    profiles = sa.table("misa_export_profiles", sa.column("id"), sa.column("code"),
                        sa.column("column_mapping", sa.JSON), sa.column("required_fields", sa.JSON),
                        sa.column("permitted_values", sa.JSON))
    connection = op.get_bind()
    for row in connection.execute(sa.select(profiles)).mappings().all():
        mapping = dict(row['column_mapping'])
        removed_column = mapping.pop('item_type', None)
        if row['code'] == 'GENERIC_DEMO' and removed_column is not None:
            mapping = {field: int(column) - (int(column) > int(removed_column))
                       for field, column in mapping.items()}
        required = [field for field in row['required_fields'] if field != 'item_type']
        permitted = {field: values for field, values in (row['permitted_values'] or {}).items()
                     if field != 'item_type'}
        connection.execute(profiles.update().where(profiles.c.id == row['id']).values(
            column_mapping=mapping, required_fields=required, permitted_values=permitted))


def downgrade() -> None:
    # Removed classification values cannot be reconstructed.
    op.add_column("product_drafts", sa.Column("item_type", sa.String(40), nullable=True))
    op.add_column("catalog_items", sa.Column("item_type", sa.String(40), nullable=False, server_default=""))
