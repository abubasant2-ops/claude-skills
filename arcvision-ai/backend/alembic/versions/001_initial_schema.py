"""initial schema + RLS policies

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- organizations ----------
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("plan", sa.Text, nullable=False, server_default="mvp"),
        sa.Column("region", sa.Text, nullable=False, server_default="sa"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ---------- users ----------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.Text),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ---------- projects ----------
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("client_name", sa.Text),
        sa.Column("project_type", sa.Text),
        sa.Column("location_city", sa.Text),
        sa.Column("gross_area_m2", sa.Numeric(14, 2)),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("sbc_profile", sa.Text),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_projects_org", "projects", ["organization_id"])

    # ---------- documents ----------
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.Text, nullable=False),
        sa.Column("file_type", sa.Text, nullable=False),
        sa.Column("discipline", sa.Text),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="uploaded"),
        sa.Column("page_count", sa.Integer),
        sa.Column("processing_meta", JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_documents_project", "documents", ["project_id"])

    # ---------- extracted_elements ----------
    op.create_table(
        "extracted_elements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("element_type", sa.Text, nullable=False),
        sa.Column("discipline", sa.Text),
        sa.Column("geometry", JSONB),
        sa.Column("source_ref", JSONB),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1.0"),
        sa.Column("extraction_method", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_elements_project", "extracted_elements", ["project_id"])
    op.create_index("ix_elements_doc", "extracted_elements", ["document_id"])

    # ---------- takeoff_items ----------
    op.create_table(
        "takeoff_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("original_quantity", sa.Numeric(14, 3)),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1.0"),
        sa.Column("source_element_ids", ARRAY(UUID(as_uuid=True))),
        sa.Column("review_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_takeoff_project", "takeoff_items", ["project_id"])

    # ---------- price_book_items ----------
    op.create_table(
        "price_book_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("material_rate", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("labor_rate", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("equipment_rate", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("waste_factor", sa.Numeric(5, 4), nullable=False, server_default="0.05"),
        sa.Column("source", sa.Text, nullable=False, server_default="market"),
        sa.Column("valid_from", sa.Date),
        sa.Column("region", sa.Text, nullable=False, server_default="sa"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_pricebook_org_cat", "price_book_items", ["organization_id", "category"])

    # ---------- cost_lines ----------
    op.create_table(
        "cost_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("takeoff_item_id", UUID(as_uuid=True), sa.ForeignKey("takeoff_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_source_id", UUID(as_uuid=True), sa.ForeignKey("price_book_items.id", ondelete="SET NULL")),
        sa.Column("material_cost", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("labor_cost", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("equipment_cost", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_costlines_project", "cost_lines", ["project_id"])

    # ---------- audit_logs ----------
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True)),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("before_state", JSONB),
        sa.Column("after_state", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_org_created", "audit_logs", ["organization_id", "created_at"])

    # ---------- Row Level Security ----------
    # Tenant isolation enforced at DB level. Backend SETs `app.current_org` per request.
    rls_tables = [
        "projects",
        "documents",
        "extracted_elements",
        "takeoff_items",
        "price_book_items",
        "cost_lines",
    ]
    for t in rls_tables:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{t} ON {t}
            USING (organization_id::text = current_setting('app.current_org', true))
            WITH CHECK (organization_id::text = current_setting('app.current_org', true));
            """
        )


def downgrade() -> None:
    rls_tables = [
        "projects",
        "documents",
        "extracted_elements",
        "takeoff_items",
        "price_book_items",
        "cost_lines",
    ]
    for t in rls_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{t} ON {t};")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;")

    for t in [
        "audit_logs",
        "cost_lines",
        "price_book_items",
        "takeoff_items",
        "extracted_elements",
        "documents",
        "projects",
        "users",
        "organizations",
    ]:
        op.drop_table(t)
