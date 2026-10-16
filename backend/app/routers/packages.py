import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.package import Package
from app.schemas.package import PackageIn, PackageOut
from app.services.storage import save_upload

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("", response_model=list[PackageOut])
def list_packages(db: Session = Depends(get_db)):
    return db.query(Package).filter(Package.is_active.is_(True)).order_by(Package.package_type).all()


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: uuid.UUID, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return package


@router.post("", response_model=PackageOut, dependencies=[Depends(require_role("admin"))])
def create_package(payload: PackageIn, db: Session = Depends(get_db)):
    package = Package(**payload.model_dump())
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


@router.put("/{package_id}", response_model=PackageOut, dependencies=[Depends(require_role("admin"))])
def update_package(package_id: uuid.UUID, payload: PackageIn, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    for field, value in payload.model_dump().items():
        setattr(package, field, value)
    db.commit()
    db.refresh(package)
    return package


@router.delete("/{package_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
def deactivate_package(package_id: uuid.UUID, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    package.is_active = False
    db.commit()


@router.post("/{package_id}/images", response_model=PackageOut, dependencies=[Depends(require_role("admin"))])
async def upload_package_image(package_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    content = await file.read()
    url = save_upload(content, "packages")
    existing = [u for u in (package.sample_image_urls or "").split(",") if u]
    existing.append(url)
    package.sample_image_urls = ",".join(existing)
    db.commit()
    db.refresh(package)
    return package


@router.delete("/{package_id}/images", response_model=PackageOut, dependencies=[Depends(require_role("admin"))])
def remove_package_image(package_id: uuid.UUID, url: str, db: Session = Depends(get_db)):
    package = db.get(Package, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    remaining = [u for u in (package.sample_image_urls or "").split(",") if u and u != url]
    package.sample_image_urls = ",".join(remaining)
    db.commit()
    db.refresh(package)
    return package
