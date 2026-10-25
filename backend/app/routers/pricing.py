"""Public pricing - the same numbers every order page shows (booking,
custom design, bulk/event order), straight from app/services/pricing.py."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.catalog import Design
from app.models.package import Package
from app.schemas.bulk_order import EstimateIn, EstimateLineOut, EstimateOut, PricingPolicyOut
from app.services.platform_settings import get_platform_settings
from app.services.pricing import order_estimate, price_band

router = APIRouter(prefix="/pricing", tags=["pricing"])


def resolve_line(db: Session, package_id: uuid.UUID, design_id: uuid.UUID | None) -> tuple[Package, Design | None]:
    package = db.get(Package, package_id)
    if package is None or not package.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    design = None
    if design_id is not None:
        design = db.get(Design, design_id)
        if design is None or not design.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found")
        if design.package_id != package.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That design belongs to a different package")
    return package, design


def estimate_out(db: Session, lines) -> EstimateOut:
    """`lines` has package_id, design_id, quantity, unit_price_min/max and
    unit_advance - an estimate line or a stored BulkOrderLine."""
    totals = order_estimate(db, [(l.unit_price_min, l.unit_price_max, l.unit_advance, l.quantity) for l in lines])
    return EstimateOut(
        lines=[
            EstimateLineOut(
                package_id=l.package_id,
                design_id=l.design_id,
                quantity=l.quantity,
                unit_price_min=l.unit_price_min,
                unit_price_max=l.unit_price_max,
                unit_advance=l.unit_advance,
            )
            for l in lines
        ],
        **totals,
    )


def priced_line(db: Session, package_id: uuid.UUID, design_id: uuid.UUID | None, quantity: int) -> EstimateLineOut:
    package, design = resolve_line(db, package_id, design_id)
    low, high = price_band(package, design)
    return EstimateLineOut(
        package_id=package.id,
        design_id=design.id if design else None,
        quantity=quantity,
        unit_price_min=low,
        unit_price_max=high,
        unit_advance=package.advance_amount or 0,
    )


@router.get("/policy", response_model=PricingPolicyOut)
def get_pricing_policy(db: Session = Depends(get_db)):
    values = get_platform_settings(db)
    return PricingPolicyOut(
        platform_fee_mode=values["platform_fee_mode"],
        platform_fee_percent=float(values["platform_fee_percent"]),
        platform_fee_flat=float(values["platform_fee_flat"]),
    )


@router.post("/estimate", response_model=EstimateOut)
def estimate(payload: EstimateIn, db: Session = Depends(get_db)):
    return estimate_out(db, [priced_line(db, l.package_id, l.design_id, l.quantity) for l in payload.lines])
