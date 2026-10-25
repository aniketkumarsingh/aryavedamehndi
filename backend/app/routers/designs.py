"""Mehndi design catalog.

- Public: browse designs by category with prices; a design's page lists
  the artists who offer it, each with their own admin-approved photo of
  having done it.
- Artists: pick catalog designs they can do and upload proof photos.
- Admin: manage the catalog and approve/reject artists' proof photos.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.time import utcnow
from app.database import get_db
from app.models.catalog import ArtistDesign, Design, DesignImage
from app.models.package import Package
from app.models.user import ArtistProfile, User
from app.schemas.catalog import (
    ArtistDesignOut,
    DesignArtistOut,
    DesignDetailOut,
    DesignImageIn,
    DesignImageOut,
    DesignIn,
    DesignOut,
    DesignPhotoRejectIn,
    DesignCoverage,
    DesignOccasion,
    DesignPhotoReviewOut,
    DesignStyle,
)
from app.services.artist_search import closest_service_point, is_bookable
from app.services.geo import estimate_travel_minutes
from app.services.notifications import notify, notify_admins
from app.services.storage import save_image_variants, save_upload

router = APIRouter(prefix="/designs", tags=["designs"])
artist_router = APIRouter(prefix="/artists", tags=["designs"])
admin_router = APIRouter(prefix="/admin/design-photos", tags=["designs"], dependencies=[Depends(require_role("admin"))])


def _approved_offers(db: Session):
    """ArtistDesign rows visible to the public: approved photo, bookable
    artist, active design."""
    return (
        db.query(ArtistDesign)
        .join(ArtistProfile, ArtistProfile.user_id == ArtistDesign.artist_id)
        .join(Design, Design.id == ArtistDesign.design_id)
        .filter(
            ArtistDesign.status == "approved",
            ArtistProfile.kyc_status == "approved",
            ArtistProfile.is_suspended.is_(False),
            ArtistProfile.base_lat.isnot(None),
            Design.is_active.is_(True),
        )
    )


def _design_out(design: Design, artist_count: int = 0) -> DesignOut:
    return DesignOut.model_validate(design).model_copy(update={"artist_count": artist_count})


def _get_design_or_404(db: Session, design_id: uuid.UUID, active_only: bool = True) -> Design:
    design = db.get(Design, design_id)
    if design is None or (active_only and not design.is_active):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found")
    return design


# ------------------------------------------------------------------ public --

@router.get("", response_model=list[DesignOut])
def list_designs(
    category: str | None = Query(None, description="package_type, e.g. bridal"),
    package_id: uuid.UUID | None = None,
    style: DesignStyle | None = None,
    coverage: DesignCoverage | None = None,
    occasion: DesignOccasion | None = None,
    db: Session = Depends(get_db),
):
    designs = _list_designs(db, category, package_id, include_inactive=False)
    return [
        d
        for d in designs
        if (style is None or d.style == style)
        and (coverage is None or d.coverage == coverage)
        and (occasion is None or occasion in d.occasions)
    ]


@router.get("/admin/all", response_model=list[DesignOut], dependencies=[Depends(require_role("admin"))])
def list_all_designs_for_admin(db: Session = Depends(get_db)):
    return _list_designs(db, None, None, include_inactive=True)


def _list_designs(db: Session, category: str | None, package_id: uuid.UUID | None, include_inactive: bool) -> list[DesignOut]:
    query = db.query(Design).join(Package, Package.id == Design.package_id)
    if not include_inactive:
        query = query.filter(Design.is_active.is_(True), Package.is_active.is_(True))
    if category:
        query = query.filter(Package.package_type == category)
    if package_id:
        query = query.filter(Design.package_id == package_id)
    designs = query.order_by(Package.package_type, Design.sort_order, Design.name).all()

    counts = dict(
        _approved_offers(db)
        .with_entities(ArtistDesign.design_id, func.count(ArtistDesign.id))
        .group_by(ArtistDesign.design_id)
        .all()
    )
    return [_design_out(d, counts.get(d.id, 0)) for d in designs]


@router.get("/{design_id}", response_model=DesignDetailOut)
def get_design(
    design_id: uuid.UUID,
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
):
    """The design plus every artist offering it. With lat/lng, only
    artists whose service area covers that point, nearest first;
    otherwise all of them, best-rated first."""
    design = _get_design_or_404(db, design_id)
    artists = []
    for offer in _approved_offers(db).filter(ArtistDesign.design_id == design_id).all():
        profile = offer.artist_profile
        distance = eta = None
        if lat is not None and lng is not None:
            distance, plat, plng = closest_service_point(db, profile, lat, lng)
            if distance > profile.service_radius_km:
                continue
            eta = estimate_travel_minutes(plat, plng, lat, lng)
            distance = round(distance, 1)
        artists.append(
            DesignArtistOut(
                artist_id=profile.user_id,
                name=profile.user.name,
                gender=profile.user.gender,
                profile_photo_url=profile.profile_photo_url,
                rating_avg=profile.rating_avg,
                rating_count=profile.rating_count,
                proof_image_url=offer.proof_image_url,
                distance_km=distance,
                eta_minutes=eta,
            )
        )
    if lat is not None and lng is not None:
        artists.sort(key=lambda a: (a.distance_km, -a.rating_avg))
    else:
        artists.sort(key=lambda a: (-a.rating_avg, -a.rating_count))

    return DesignDetailOut(
        **_design_out(design, len(artists)).model_dump(),
        images=[DesignImageOut.model_validate(i) for i in design.images if i.kind != "spin"],
        spin_frames=[DesignImageOut.model_validate(i) for i in design.images if i.kind == "spin"],
        artists=artists,
    )


@artist_router.get("/me/designs", response_model=list[ArtistDesignOut])
def list_my_designs(user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    return db.query(ArtistDesign).filter(ArtistDesign.artist_id == user.id).order_by(ArtistDesign.created_at.desc()).all()


@artist_router.post("/me/designs/{design_id}", response_model=ArtistDesignOut)
async def offer_design(
    design_id: uuid.UUID,
    file: UploadFile = File(...),
    catalog_consent: bool = Form(False),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    """Offer a catalog design with a photo of your own work. Uploading a
    new photo for a design you already offer replaces it and sends it back
    for review. `catalog_consent` lets AryaVeda use the photo as the
    design's main catalog photo."""
    if db.get(ArtistProfile, user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")
    design = _get_design_or_404(db, design_id)
    proof_url = save_upload(await file.read(), "design-proofs")

    offer = db.query(ArtistDesign).filter(ArtistDesign.artist_id == user.id, ArtistDesign.design_id == design_id).first()
    if offer is None:
        offer = ArtistDesign(artist_id=user.id, design_id=design_id, proof_image_url=proof_url)
        db.add(offer)
    offer.proof_image_url = proof_url
    offer.catalog_consent = catalog_consent
    offer.status = "pending"
    offer.rejection_reason = None
    offer.reviewed_at = None
    notify_admins(db, "Design photo to review", f"{user.name or 'An artist'} submitted a photo for \"{design.name}\".", "/admin")
    db.commit()
    db.refresh(offer)
    return offer


@artist_router.delete("/me/designs/{design_id}", status_code=204)
def stop_offering_design(design_id: uuid.UUID, user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    """Existing bookings for this design are unaffected - only new
    bookings need an approved offer."""
    offer = db.query(ArtistDesign).filter(ArtistDesign.artist_id == user.id, ArtistDesign.design_id == design_id).first()
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You don't offer this design")
    db.delete(offer)
    db.commit()


@artist_router.get("/{artist_id}/designs", response_model=list[ArtistDesignOut])
def list_artist_designs(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    """An artist's approved designs, for their public profile and the
    booking form's design picker."""
    profile = db.get(ArtistProfile, artist_id)
    if profile is None or not is_bookable(profile):
        return []
    return (
        _approved_offers(db)
        .filter(ArtistDesign.artist_id == artist_id)
        .order_by(Design.package_id, Design.sort_order, Design.name)
        .all()
    )


# ------------------------------------------------------------ admin catalog --

@router.post("", response_model=DesignOut, dependencies=[Depends(require_role("admin"))])
def create_design(payload: DesignIn, db: Session = Depends(get_db)):
    if db.get(Package, payload.package_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Package not found")
    design = Design(**payload.model_dump())
    db.add(design)
    db.commit()
    db.refresh(design)
    return _design_out(design)


@router.put("/{design_id}", response_model=DesignOut, dependencies=[Depends(require_role("admin"))])
def update_design(design_id: uuid.UUID, payload: DesignIn, db: Session = Depends(get_db)):
    """Price changes apply to new bookings - confirmed bookings keep the
    price they agreed."""
    design = _get_design_or_404(db, design_id, active_only=False)
    if db.get(Package, payload.package_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Package not found")
    for field, value in payload.model_dump().items():
        setattr(design, field, value)
    db.commit()
    db.refresh(design)
    return _design_out(design)


@router.delete("/{design_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
def deactivate_design(design_id: uuid.UUID, db: Session = Depends(get_db)):
    design = _get_design_or_404(db, design_id, active_only=False)
    design.is_active = False
    db.commit()


@router.post("/{design_id}/image", response_model=DesignOut, dependencies=[Depends(require_role("admin"))])
async def upload_design_image(design_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Replaces the main photo (the verification reference)."""
    design = _get_design_or_404(db, design_id, active_only=False)
    design.image_url, design.image_hd_url = save_image_variants(await file.read(), "catalog")
    design.image_source = None
    design.image_kind, design.image_credit = "photo", None
    design.photo_needed = None
    db.commit()
    db.refresh(design)
    return _design_out(design)


# ------------------------------------------------------- admin gallery views --

@router.get("/{design_id}/gallery", response_model=list[DesignImageOut], dependencies=[Depends(require_role("admin"))])
def list_gallery(design_id: uuid.UUID, db: Session = Depends(get_db)):
    return [i for i in _get_design_or_404(db, design_id, active_only=False).images if i.kind != "spin"]


@router.post("/{design_id}/gallery", response_model=DesignImageOut, dependencies=[Depends(require_role("admin"))])
async def add_gallery_image(
    design_id: uuid.UUID,
    file: UploadFile = File(...),
    label: str | None = Form(None, max_length=80),
    kind: str = Form("photo"),
    db: Session = Depends(get_db),
):
    try:
        meta = DesignImageIn(label=label or None, kind=kind)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors(include_url=False)) from exc
    design = _get_design_or_404(db, design_id, active_only=False)
    next_order = max((i.sort_order for i in design.images), default=-1) + 1
    url, hd_url = save_image_variants(await file.read(), "catalog")
    image = DesignImage(
        design_id=design.id,
        url=url,
        hd_url=hd_url,
        label=meta.label,
        kind=meta.kind,
        sort_order=next_order,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def _get_gallery_image(db: Session, design_id: uuid.UUID, image_id: uuid.UUID) -> DesignImage:
    image = db.get(DesignImage, image_id)
    if image is None or image.design_id != design_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gallery image not found")
    return image


@router.delete("/{design_id}/gallery/{image_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
def remove_gallery_image(design_id: uuid.UUID, image_id: uuid.UUID, db: Session = Depends(get_db)):
    db.delete(_get_gallery_image(db, design_id, image_id))
    db.commit()


# ------------------------------------------------------ admin 360 frames --

MAX_SPIN_FRAMES = 72


@router.put("/{design_id}/spin", response_model=list[DesignImageOut], dependencies=[Depends(require_role("admin"))])
async def replace_spin_frames(design_id: uuid.UUID, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Replaces the 360-degree view with a new set of turntable frames,
    ordered by file name (01.jpg, 02.jpg, ... - one photo every 10-15
    degrees all the way round)."""
    design = _get_design_or_404(db, design_id, active_only=False)
    if not 8 <= len(files) <= MAX_SPIN_FRAMES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Upload between 8 and {MAX_SPIN_FRAMES} frames for a smooth 360 view")
    frames = []
    for order, f in enumerate(sorted(files, key=lambda f: f.filename or "")):
        url, hd_url = save_image_variants(await f.read(), "catalog")
        frames.append(DesignImage(design_id=design.id, url=url, hd_url=hd_url, kind="spin", sort_order=order, label=f"Frame {order + 1}"))
    db.query(DesignImage).filter(DesignImage.design_id == design.id, DesignImage.kind == "spin", DesignImage.source_key.is_(None)).delete()
    db.add_all(frames)
    db.commit()
    return frames


@router.delete("/{design_id}/spin", status_code=204, dependencies=[Depends(require_role("admin"))])
def clear_spin_frames(design_id: uuid.UUID, db: Session = Depends(get_db)):
    design = _get_design_or_404(db, design_id, active_only=False)
    db.query(DesignImage).filter(DesignImage.design_id == design.id, DesignImage.kind == "spin", DesignImage.source_key.is_(None)).delete()
    db.commit()


@router.post("/{design_id}/gallery/{image_id}/make-main", response_model=DesignOut, dependencies=[Depends(require_role("admin"))])
def make_gallery_image_main(design_id: uuid.UUID, image_id: uuid.UUID, db: Session = Depends(get_db)):
    """Swaps a gallery view with the main photo - the old main photo stays
    in the gallery in its place. Bookings already made keep the reference
    they were made with."""
    design = _get_design_or_404(db, design_id, active_only=False)
    image = _get_gallery_image(db, design_id, image_id)
    if image.kind in ("ai_photo", "spin"):
        # The main image is what finished work is checked against - an AI
        # preview or a turntable frame must never become that reference.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This view can't be the main image - upload a real photo instead")
    old = (design.image_url, design.image_hd_url, design.image_source, design.image_kind, design.image_credit)
    design.image_url, design.image_hd_url, design.image_source = image.url, image.hd_url, image.source_key
    design.image_kind = "illustration" if image.kind == "illustration" else "photo"
    design.image_credit = image.credit
    if old[0]:
        image.url, image.hd_url, image.source_key, old_kind, image.credit = old
        image.kind = "illustration" if old_kind == "illustration" else "photo"
        image.label = "Previous main illustration" if image.kind == "illustration" else "Previous main photo"
    else:
        db.delete(image)
    db.commit()
    db.refresh(design)
    return _design_out(design)


# ------------------------------------------------------ admin photo review --

def _review_out(offer: ArtistDesign) -> DesignPhotoReviewOut:
    user = offer.artist_profile.user
    return DesignPhotoReviewOut(
        **ArtistDesignOut.model_validate(offer).model_dump(),
        artist_id=offer.artist_id,
        artist_name=user.name,
        artist_phone=user.phone,
    )


@admin_router.get("", response_model=list[DesignPhotoReviewOut])
def list_design_photos(
    status_filter: str = Query("pending", pattern="^(pending|approved|rejected|all)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(ArtistDesign).order_by(ArtistDesign.created_at)
    if status_filter != "all":
        query = query.filter(ArtistDesign.status == status_filter)
    return [_review_out(o) for o in query.offset(offset).limit(limit).all()]


def _get_offer_or_404(db: Session, offer_id: uuid.UUID) -> ArtistDesign:
    offer = db.get(ArtistDesign, offer_id)
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design photo not found")
    return offer


@admin_router.post("/{offer_id}/approve", response_model=DesignPhotoReviewOut)
def approve_design_photo(offer_id: uuid.UUID, db: Session = Depends(get_db)):
    offer = _get_offer_or_404(db, offer_id)
    offer.status = "approved"
    offer.rejection_reason = None
    offer.reviewed_at = utcnow()
    notify(db, offer.artist_id, "system", "Design photo approved", f"Customers can now book you for \"{offer.design.name}\".", "/artist/profile")
    db.commit()
    db.refresh(offer)
    return _review_out(offer)


@admin_router.post("/{offer_id}/reject", response_model=DesignPhotoReviewOut)
def reject_design_photo(offer_id: uuid.UUID, payload: DesignPhotoRejectIn, db: Session = Depends(get_db)):
    offer = _get_offer_or_404(db, offer_id)
    offer.status = "rejected"
    offer.rejection_reason = payload.reason
    offer.reviewed_at = utcnow()
    notify(db, offer.artist_id, "system", "Design photo not approved", f"\"{offer.design.name}\": {payload.reason}", "/artist/profile")
    db.commit()
    db.refresh(offer)
    return _review_out(offer)


@admin_router.post("/{offer_id}/use-as-catalog", response_model=DesignOut)
def use_photo_as_catalog(offer_id: uuid.UUID, db: Session = Depends(get_db)):
    """Makes an artist's approved real photo the design's main catalog
    photo (and so the reference finished work is checked against) - only
    with the artist's consent. The previous main photo stays in the
    gallery. seed_designs.py never overwrites a photo set this way."""
    offer = _get_offer_or_404(db, offer_id)
    if offer.status != "approved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Approve the photo first")
    if not offer.catalog_consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The artist hasn't allowed this photo to be used as the catalog photo")
    design = offer.design
    if design.image_url == offer.proof_image_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This photo is already the catalog photo")
    if design.image_url:
        next_order = max((i.sort_order for i in design.images), default=-1) + 1
        db.add(DesignImage(design_id=design.id, url=design.image_url, hd_url=design.image_hd_url, label="Previous catalog photo", kind="photo", sort_order=next_order))
    design.image_url, design.image_hd_url, design.image_source = offer.proof_image_url, None, None
    design.photo_needed = None
    notify(db, offer.artist_id, "system", "Your photo is now the catalog photo", f"Customers now see your work as the main photo for \"{design.name}\".", f"/designs/{design.id}")
    db.commit()
    db.refresh(design)
    return _design_out(design)
