"""initial watchlist schema

Revision ID: 0001
Revises:
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("default_shop_id", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "watched_products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("name_cache", sa.String(length=512), nullable=False),
        sa.Column("url_key", sa.String(length=512), nullable=True),
        sa.Column(
            "notify_min_discount_percent",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "source", "sku", "shop_id", name="uq_watchlist_item"
        ),
    )
    op.create_index(
        "ix_watched_products_user_id", "watched_products", ["user_id"]
    )
    op.create_index("ix_watched_products_sku", "watched_products", ["sku"])

    op.create_table(
        "product_state",
        sa.Column("source", sa.String(length=32), primary_key=True),
        sa.Column("sku", sa.String(length=64), primary_key=True),
        sa.Column("shop_id", sa.Integer(), primary_key=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("special_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("discount_percent", sa.Integer(), nullable=True),
        sa.Column("special_price_to_date", sa.Date(), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "notifications_sent",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("discount_percent_at_notify", sa.Integer(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_notifications_sent_user_id", "notifications_sent", ["user_id"]
    )
    op.create_index("ix_notifications_sent_sku", "notifications_sent", ["sku"])


def downgrade() -> None:
    op.drop_index("ix_notifications_sent_sku", table_name="notifications_sent")
    op.drop_index("ix_notifications_sent_user_id", table_name="notifications_sent")
    op.drop_table("notifications_sent")
    op.drop_table("product_state")
    op.drop_index("ix_watched_products_sku", table_name="watched_products")
    op.drop_index("ix_watched_products_user_id", table_name="watched_products")
    op.drop_table("watched_products")
    op.drop_table("users")
