
"""add company customer order data

Revision ID: xxxxxxxxxxxx
Revises: 761c1659a84d
Create Date: 2026-09-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "xxxxxxxxxxxx"
down_revision: Union[str, Sequence[str], None] = "761c1659a84d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # =========================================================
    # COMPANIES
    # =========================================================

    op.create_table(
        "companies",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "company_code",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "company_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "domain",
            sa.String(length=320),
            nullable=True,
        ),

        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=True,
        ),

        # Best-practice audit fields
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_code",
            name="uq_companies_company_code",
        ),
    )

    op.create_index(
        "ix_companies_company_code",
        "companies",
        ["company_code"],
        unique=True,
    )

    op.create_index(
        "ix_companies_domain",
        "companies",
        ["domain"],
        unique=False,
    )


    # =========================================================
    # CUSTOMERS
    # =========================================================

    op.create_table(
        "customers",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "company_id",
            sa.Integer(),
            nullable=False,
        ),

        # Business/customer identifier
        sa.Column(
            "customer_id",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "email",
            sa.String(length=320),
            nullable=True,
        ),

        sa.Column(
            "phone",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "address",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="active",
        ),

        # Best-practice fields
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "created_by",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "updated_by",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "source_system",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "company_id",
            "customer_id",
            name="uq_customers_company_customer",
        ),
    )

    op.create_index(
        "ix_customers_company_id",
        "customers",
        ["company_id"],
    )

    op.create_index(
        "ix_customers_customer_id",
        "customers",
        ["customer_id"],
    )

    op.create_index(
        "ix_customers_email",
        "customers",
        ["email"],
    )


    # =========================================================
    # ORDERS
    # =========================================================

    op.create_table(
        "orders",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "company_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=False,
        ),

        # PRIMARY BUSINESS KEY
        sa.Column(
            "order_id",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "external_reference",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "payment_status",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "fulfillment_status",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "currency",
            sa.String(length=10),
            nullable=False,
            server_default="INR",
        ),

        sa.Column(
            "total_amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        sa.Column(
            "shipping_address",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "tracking_number",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "estimated_delivery",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # Best-practice business fields
        sa.Column(
            "cancellation_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),

        sa.Column(
            "refund_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),

        sa.Column(
            "return_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),

        # Audit fields
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "created_by",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "updated_by",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "source_system",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "company_id",
            "order_id",
            name="uq_orders_company_order",
        ),
    )

    op.create_index(
        "ix_orders_company_id",
        "orders",
        ["company_id"],
    )

    op.create_index(
        "ix_orders_customer_id",
        "orders",
        ["customer_id"],
    )

    op.create_index(
        "ix_orders_order_id",
        "orders",
        ["order_id"],
    )

    op.create_index(
        "ix_orders_tracking_number",
        "orders",
        ["tracking_number"],
    )


    # =========================================================
    # ORDER ITEMS
    # =========================================================

    op.create_table(
        "order_items",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "order_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "product_id",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "product_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "unit_price",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_order_items_order_id",
        "order_items",
        ["order_id"],
    )


    # =========================================================
    # ORDER EVENTS
    # =========================================================

    op.create_table(
        "order_events",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "order_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "event_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_order_events_order_id",
        "order_events",
        ["order_id"],
    )

    op.create_index(
        "ix_order_events_event_at",
        "order_events",
        ["event_at"],
    )


def downgrade() -> None:

    op.drop_index(
        "ix_order_events_event_at",
        table_name="order_events",
    )

    op.drop_index(
        "ix_order_events_order_id",
        table_name="order_events",
    )

    op.drop_table("order_events")

    op.drop_index(
        "ix_order_items_order_id",
        table_name="order_items",
    )

    op.drop_table("order_items")

    op.drop_index(
        "ix_orders_tracking_number",
        table_name="orders",
    )

    op.drop_index(
        "ix_orders_order_id",
        table_name="orders",
    )

    op.drop_index(
        "ix_orders_customer_id",
        table_name="orders",
    )

    op.drop_index(
        "ix_orders_company_id",
        table_name="orders",
    )

    op.drop_table("orders")

    op.drop_index(
        "ix_customers_email",
        table_name="customers",
    )

    op.drop_index(
        "ix_customers_customer_id",
        table_name="customers",
    )

    op.drop_index(
        "ix_customers_company_id",
        table_name="customers",
    )

    op.drop_table("customers")

    op.drop_index(
        "ix_companies_domain",
        table_name="companies",
    )

    op.drop_index(
        "ix_companies_company_code",
        table_name="companies",
    )

    op.drop_table("companies")

