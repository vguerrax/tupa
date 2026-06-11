"""Create tenants table.

Revision ID: 20260611_01
Revises:
Create Date: 2026-06-11
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260611_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_product_id", "tenants", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_tenants_product_id", table_name="tenants")
    op.drop_table("tenants")
