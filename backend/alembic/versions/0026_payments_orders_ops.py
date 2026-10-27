"""payments & orders operations: job queue, payment event inbox, refunds,
reconciliation, idempotency keys; order payment status, COD, credit notes

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-26
migration-safe: shipped before rolling deploys (scripts/check_migrations.py); reviewed.

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(160), nullable=True, unique=True),
        sa.Column("locked_by", sa.String(80), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])

    op.create_table(
        "payment_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False, server_default="razorpay"),
        sa.Column("event_id", sa.String(100), nullable=False, unique=True),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="received"),
        sa.Column("result", sa.String(120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_payment_events_received_at", "payment_events", ["received_at"])

    op.create_table(
        "refunds",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID, nullable=False),
        sa.Column("razorpay_payment_id", sa.String(100), nullable=False),
        sa.Column("razorpay_refund_id", sa.String(100), nullable=True, unique=True),
        sa.Column("amount_requested", sa.Float(), nullable=True),
        sa.Column("amount_refunded", sa.Float(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("initiated_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("credit_note_number", sa.String(16), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_refunds_target_id", "refunds", ["target_id"])
    op.create_index("ix_refunds_razorpay_payment_id", "refunds", ["razorpay_payment_id"])

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("window_from", sa.DateTime(), nullable=False),
        sa.Column("window_to", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="running"),
        sa.Column("payments_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fixed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issues", JSONB, nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])

    # --- shop orders: payment status apart from fulfilment status, COD ---
    for name, type_, default in (
        ("payment_method", sa.String(10), "online"),
        ("payment_status", sa.String(20), "unpaid"),
        ("amount_paid", sa.Float(), "0"),
        ("amount_refunded", sa.Float(), "0"),
        ("cod_fee", sa.Float(), "0"),
    ):
        op.add_column("shop_orders", sa.Column(name, type_, nullable=False, server_default=default))
    op.add_column("shop_orders", sa.Column("contact_email", sa.String(200), nullable=True))
    op.add_column("shop_orders", sa.Column("confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("shop_orders", sa.Column("delivered_at", sa.DateTime(), nullable=True))
    op.add_column("shop_orders", sa.Column("invoiced_at", sa.DateTime(), nullable=True))

    # Existing orders: "paid" becomes "confirmed"; money moved -> "paid".
    op.execute("""
        UPDATE shop_orders SET
          payment_status = CASE
            WHEN refund_status = 'refunded' THEN 'refunded'
            WHEN paid_at IS NOT NULL AND status = 'cancelled' THEN 'refund_pending'
            WHEN paid_at IS NOT NULL THEN 'paid'
            WHEN status = 'cancelled' THEN 'void'
            ELSE 'unpaid' END,
          amount_paid = CASE WHEN paid_at IS NOT NULL THEN total_amount ELSE 0 END,
          amount_refunded = CASE WHEN refund_status = 'refunded' THEN total_amount ELSE 0 END,
          confirmed_at = paid_at,
          invoiced_at = CASE WHEN invoice_number IS NOT NULL THEN paid_at END,
          status = CASE WHEN status = 'paid' THEN 'confirmed' ELSE status END
    """)
    # Refunds recorded on the order move into the refunds table.
    op.execute("""
        INSERT INTO refunds (id, target_type, target_id, razorpay_payment_id, razorpay_refund_id, amount_refunded,
                             status, reason, failure_reason, created_at, updated_at, processed_at)
        SELECT gen_random_uuid(), 'shop_order', id, razorpay_payment_id, refund_id,
               CASE WHEN refund_status = 'refunded' THEN total_amount END,
               CASE WHEN refund_status = 'refunded' THEN 'processed' ELSE 'failed' END,
               cancel_reason,
               CASE WHEN refund_status = 'failed' THEN 'Recorded before refunds were tracked' END,
               COALESCE(cancelled_at, created_at), COALESCE(cancelled_at, created_at),
               CASE WHEN refund_status = 'refunded' THEN cancelled_at END
        FROM shop_orders WHERE refund_status IS NOT NULL AND razorpay_payment_id IS NOT NULL
    """)
    op.drop_column("shop_orders", "refund_id")
    op.drop_column("shop_orders", "refund_status")
    op.create_index("ix_shop_orders_payment_status", "shop_orders", ["payment_status"])

    # Counters become per document series: "2627" -> "INV2627".
    op.alter_column("shop_invoice_counters", "financial_year", new_column_name="series", type_=sa.String(12))
    op.execute("UPDATE shop_invoice_counters SET series = 'INV' || series WHERE series NOT LIKE 'INV%'")


def downgrade() -> None:
    op.execute("UPDATE shop_invoice_counters SET series = substr(series, 4) WHERE series LIKE 'INV%'")
    op.execute("DELETE FROM shop_invoice_counters WHERE series LIKE 'CN%'")
    op.alter_column("shop_invoice_counters", "series", new_column_name="financial_year", type_=sa.String(4))
    op.drop_index("ix_shop_orders_payment_status", table_name="shop_orders")
    op.add_column("shop_orders", sa.Column("refund_status", sa.String(20), nullable=True))
    op.add_column("shop_orders", sa.Column("refund_id", sa.String(100), nullable=True))
    op.execute("""
        UPDATE shop_orders o SET refund_status = CASE r.status WHEN 'processed' THEN 'refunded' ELSE 'failed' END,
                                 refund_id = r.razorpay_refund_id
        FROM refunds r WHERE r.target_type = 'shop_order' AND r.target_id = o.id
    """)
    op.execute("UPDATE shop_orders SET status = 'paid' WHERE status = 'confirmed' AND payment_status = 'paid'")
    op.execute("UPDATE shop_orders SET status = 'pending' WHERE status = 'confirmed'")
    for name in ("invoiced_at", "delivered_at", "confirmed_at", "contact_email", "cod_fee", "amount_refunded",
                 "amount_paid", "payment_status", "payment_method"):
        op.drop_column("shop_orders", name)
    op.drop_table("idempotency_keys")
    op.drop_table("reconciliation_runs")
    op.drop_table("refunds")
    op.drop_table("payment_events")
    op.drop_table("jobs")
