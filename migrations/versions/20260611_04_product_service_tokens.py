"""Add per-product service tokens.

Revision ID: 20260611_04
Revises: 20260611_03
Create Date: 2026-06-11
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260611_04"
down_revision: str | None = "20260611_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("service_token_hash", sa.String(64)))
    op.add_column("products", sa.Column("service_token_hint", sa.String(12)))
    op.create_unique_constraint(
        "uq_products_service_token_hash", "products", ["service_token_hash"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_service_token_hash", "products", type_="unique")
    op.drop_column("products", "service_token_hint")
    op.drop_column("products", "service_token_hash")
