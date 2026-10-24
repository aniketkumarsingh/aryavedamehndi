from sqlalchemy.orm import Session

from app.models.artist_location import ArtistLocation
from app.models.user import ArtistProfile
from app.services.geo import haversine_km


def closest_service_point(db: Session, profile: ArtistProfile, lat: float, lng: float) -> tuple[float, float, float]:
    """(distance_km, point_lat, point_lng) to whichever of the artist's
    service locations - primary base plus any extra ArtistLocations - is
    closest to (lat, lng)."""
    points = [(profile.base_lat, profile.base_lng)]
    points += [(loc.lat, loc.lng) for loc in db.query(ArtistLocation).filter(ArtistLocation.artist_id == profile.user_id).all()]

    best = None
    for plat, plng in points:
        d = haversine_km(lat, lng, plat, plng)
        if best is None or d < best[0]:
            best = (d, plat, plng)
    return best


def is_bookable(profile: ArtistProfile) -> bool:
    return profile.kyc_status == "approved" and not profile.is_suspended and profile.base_lat is not None
