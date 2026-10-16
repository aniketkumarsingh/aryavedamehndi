import math

import httpx

from app.config import get_settings

settings = get_settings()

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Used for nearest-artist search instead
    of PostGIS, which isn't installed on this machine yet - accurate enough
    for city-scale radius search; swap in PostGIS ST_DWithin if/when it's
    added, without changing the API shape."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_travel_minutes(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> int:
    """Travel time in minutes from the artist's base location to the
    booking address. Uses Google Distance Matrix when a key is configured;
    otherwise falls back to a straight-line estimate at 25 km/h (typical
    mixed city traffic speed for two/three-wheelers)."""
    if settings.google_maps_api_key:
        try:
            return _google_distance_matrix_minutes(origin_lat, origin_lng, dest_lat, dest_lng)
        except Exception:
            pass  # fall through to the estimate below

    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    avg_speed_kmh = 25
    return max(5, round(distance_km / avg_speed_kmh * 60))


def _google_distance_matrix_minutes(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> int:
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": f"{origin_lat},{origin_lng}",
        "destinations": f"{dest_lat},{dest_lng}",
        "key": settings.google_maps_api_key,
    }
    with httpx.Client(timeout=10) as client:
        resp = client.get(url, params=params)
    data = resp.json()
    seconds = data["rows"][0]["elements"][0]["duration"]["value"]
    return max(5, round(seconds / 60))
