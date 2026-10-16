import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.favorite import Favorite
from app.models.user import ArtistProfile, User
from app.schemas.favorite import FavoriteArtistOut

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=list[FavoriteArtistOut])
def list_favorites(user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    rows = db.query(Favorite).filter(Favorite.consumer_id == user.id).order_by(Favorite.created_at.desc()).all()
    results = []
    for fav in rows:
        profile = db.get(ArtistProfile, fav.artist_id)
        if profile is None:
            continue
        results.append(
            FavoriteArtistOut(
                artist_id=fav.artist_id,
                name=profile.user.name,
                gender=profile.user.gender,
                bio=profile.bio,
                profile_photo_url=profile.profile_photo_url,
                rating_avg=profile.rating_avg,
                rating_count=profile.rating_count,
                favorited_at=fav.created_at,
            )
        )
    return results


@router.post("/{artist_id}", status_code=204)
def add_favorite(artist_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    if db.get(ArtistProfile, artist_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    existing = db.query(Favorite).filter(Favorite.consumer_id == user.id, Favorite.artist_id == artist_id).first()
    if existing is None:
        db.add(Favorite(consumer_id=user.id, artist_id=artist_id))
        db.commit()


@router.delete("/{artist_id}", status_code=204)
def remove_favorite(artist_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    db.query(Favorite).filter(Favorite.consumer_id == user.id, Favorite.artist_id == artist_id).delete()
    db.commit()
