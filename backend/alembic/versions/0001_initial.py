"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="consumer"),
        sa.Column("gender", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "artist_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("service_radius_km", sa.Float, server_default="10"),
        sa.Column("base_lat", sa.Float, nullable=True),
        sa.Column("base_lng", sa.Float, nullable=True),
        sa.Column("kyc_status", sa.String(20), server_default="pending"),
        sa.Column("kyc_doc_url", sa.String(500), nullable=True),
        sa.Column("kyc_selfie_url", sa.String(500), nullable=True),
        sa.Column("portfolio_urls", sa.Text, nullable=True),
        sa.Column("rating_avg", sa.Float, server_default="0"),
        sa.Column("rating_count", sa.Integer, server_default="0"),
        sa.Column("strike_count", sa.Integer, server_default="0"),
        sa.Column("is_suspended", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("package_type", sa.String(30), nullable=False, server_default="regular"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price_min", sa.Float, nullable=False),
        sa.Column("price_max", sa.Float, nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("negotiable", sa.Boolean, server_default=sa.true()),
        sa.Column("sample_image_urls", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "artist_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artist_profiles.user_id"), nullable=False),
        sa.Column("slot_date", sa.Date, nullable=False),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("artist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artist_profiles.user_id"), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("status", sa.String(30), server_default="requested"),
        sa.Column("address_text", sa.Text, nullable=True),
        sa.Column("location_lat", sa.Float, nullable=False),
        sa.Column("location_lng", sa.Float, nullable=False),
        sa.Column("scheduled_at", sa.DateTime, nullable=False),
        sa.Column("eta_minutes", sa.Float, nullable=True),
        sa.Column("gender_preference", sa.String(10), server_default="same"),
        sa.Column("reference_design_image_url", sa.String(500), nullable=True),
        sa.Column("agreed_price", sa.Float, nullable=True),
        sa.Column("platform_fee", sa.Float, nullable=True),
        sa.Column("total_amount", sa.Float, nullable=True),
        sa.Column("artist_arrived_at", sa.DateTime, nullable=True),
        sa.Column("artist_arrived_lat", sa.Float, nullable=True),
        sa.Column("artist_arrived_lng", sa.Float, nullable=True),
        sa.Column("artist_completed_at", sa.DateTime, nullable=True),
        sa.Column("artist_completed_lat", sa.Float, nullable=True),
        sa.Column("artist_completed_lng", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "negotiation_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("proposed_by", sa.String(10), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "design_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False, unique=True),
        sa.Column("completed_image_url", sa.String(500), nullable=False),
        sa.Column("reference_image_url", sa.String(500), nullable=True),
        sa.Column("similarity_score", sa.Float, nullable=True),
        sa.Column("match_status", sa.String(30), server_default="needs_consumer_confirmation"),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False, unique=True),
        sa.Column("razorpay_order_id", sa.String(100), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(100), nullable=True),
        sa.Column("razorpay_signature", sa.String(200), nullable=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("currency", sa.String(10), server_default="INR"),
        sa.Column("status", sa.String(20), server_default="created"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("by_role", sa.String(10), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("reported_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "cms_content",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("content", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_by", sa.String(120), nullable=True),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "otp_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("is_used", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_otp_codes_phone", "otp_codes", ["phone"])


def downgrade() -> None:
    op.drop_table("otp_codes")
    op.drop_table("cms_content")
    op.drop_table("reports")
    op.drop_table("reviews")
    op.drop_table("payments")
    op.drop_table("design_uploads")
    op.drop_table("negotiation_offers")
    op.drop_table("bookings")
    op.drop_table("artist_availability")
    op.drop_table("packages")
    op.drop_table("artist_profiles")
    op.drop_table("users")
