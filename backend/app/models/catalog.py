import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.database import Base


class Design(Base):
    """One mehndi design in the admin-curated catalog.

    Belongs to a package, which gives it its category (package_type:
    bridal/party/regular/feet/kids/groom). Style, coverage and occasions
    are filters across categories (allowed values: app/schemas/catalog.py).
    Has its own price range and
    duration - when a consumer books a design, its range replaces the
    package's for negotiation, and its image becomes the reference the
    finished photo is scored against (see app/routers/bookings.py).
    """

    __tablename__ = "designs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # The main photo - also the reference the finished work is scored
    # against. Extra views live in DesignImage (see `images`).
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Full-resolution original of the main photo, loaded only when zooming
    # (image_url is the light display copy). Null when the upload was
    # already small enough to serve directly.
    image_hd_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Which catalog file the main photo came from ("<file>:<sha>"), so
    # seed_designs.py can tell when the source changed and re-upload it.
    # Null for photos an admin uploaded.
    image_source: Mapped[str] = mapped_column(String(200), nullable=True)
    # "photo" (a real photo - the verification reference) or "illustration"
    # (a labelled AI illustration standing in until a real photo exists; never
    # used as the reference a finished design is scored against).
    image_kind: Mapped[str] = mapped_column(String(20), default="photo", server_default="photo")
    # Credit the main image's licence requires, shown next to it:
    # {"author", "license", "license_url", "source_url", "edited"} for
    # licensed photos, {"generator"} for illustrations. Null = no credit needed.
    image_credit: Mapped[dict] = mapped_column(JSONB, nullable=True)
    price_min: Mapped[float] = mapped_column(Float, nullable=False)
    price_max: Mapped[float] = mapped_column(Float, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # e.g. "arabic", "rajasthani"
    style: Mapped[str] = mapped_column(String(30), nullable=True)
    # How much of the hand/foot it covers, e.g. "palm", "elbow"
    coverage: Mapped[str] = mapped_column(String(30), nullable=True)
    # Occasions it suits, e.g. ["wedding", "karwa-chauth"]
    occasions: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list, server_default="{}")
    # Set while the design is hidden for lack of a good photo - what photo
    # is needed. Cleared when an admin uploads a main photo.
    photo_needed: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    package: Mapped["Package"] = relationship(viewonly=True)
    images: Mapped[list["DesignImage"]] = relationship(
        order_by="(DesignImage.sort_order, DesignImage.created_at)", viewonly=True
    )

    @property
    def category(self) -> str | None:
        return self.package.package_type if self.package else None

    @property
    def image_count(self) -> int:
        return (1 if self.image_url else 0) + sum(1 for i in self.images if i.kind != "spin")

    @property
    def spin_frame_count(self) -> int:
        return sum(1 for i in self.images if i.kind == "spin")


# DesignImage.kind - "spin" frames are the ordered photos of a 360-degree
# turntable shot (see the design page's 360 viewer), not gallery views.
DESIGN_IMAGE_KINDS = ("photo", "angle", "detail", "illustration", "spin")


class DesignImage(Base):
    """An extra gallery view of a design - another angle, a close-up of the
    detail, or an illustrated version - shown alongside the main photo so a
    customer can inspect the design before booking."""

    __tablename__ = "design_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="CASCADE"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Full-resolution original for zooming (see Design.image_hd_url).
    hd_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # e.g. "Palm close-up", "Side view", "Illustrated version"
    label: Mapped[str] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="photo")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Set for images loaded by seed_designs.py ("<slug>/<file>:<sha>") so a
    # re-run can sync them; null for images an admin uploaded by hand.
    source_key: Mapped[str] = mapped_column(String(200), nullable=True)
    # Licence credit shown with the image (see Design.image_credit).
    credit: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ArtistDesign.status
ARTIST_DESIGN_STATUSES = ("pending", "approved", "rejected")


class ArtistDesign(Base):
    """An artist saying "I can do this catalog design", backed by their own
    photo of having done it. Only shown publicly once an admin approves the
    photo as genuinely the artist's work - and only an approved link lets a
    consumer book that artist for that design."""

    __tablename__ = "artist_designs"
    __table_args__ = (UniqueConstraint("artist_id", "design_id", name="uq_artist_design"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artist_profiles.user_id"), index=True, nullable=False)
    design_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id"), index=True, nullable=False)
    proof_image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    # The artist allows AryaVeda to use this photo as the design's main
    # catalog photo (see POST /admin/design-photos/{id}/use-as-catalog).
    catalog_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    design: Mapped[Design] = relationship(viewonly=True)
    artist_profile: Mapped["ArtistProfile"] = relationship(viewonly=True)
