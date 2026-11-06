"""Géocodage adresse vers coordonnées avec geopy + Nominatim (OpenStreetMap, gratuit).

Chaque adresse trouvée est gardée 30 jours en mémoire (point 16) et le nombre d'appels par jour est plafonné
(point 02, GEOCODER_DAILY_LIMIT). Le service a 5 secondes pour répondre (point 08) ; sinon on continue sans carte.
"""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

from core import quotas

logger = logging.getLogger(__name__)

FOUND_SECONDS = 60 * 60 * 24 * 30
NOT_FOUND_SECONDS = 60 * 60 * 24
MISSING = "-"


def _cache_key(address):
    normalized = " ".join(address.lower().split())
    return "geo:" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def geocode_address(address):
    """Retourne (latitude, longitude) ou None si l'adresse est introuvable ou le service indisponible."""
    if not address:
        return None
    key = _cache_key(address)
    known = cache.get(key)
    if known == MISSING:
        return None
    if known:
        return tuple(known)
    try:
        quotas.take("geocoder", settings.GEOCODER_DAILY_LIMIT)
    except quotas.QuotaExceeded:
        return None
    try:
        from geopy.exc import GeopyError
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent=settings.GEOCODER_USER_AGENT, timeout=5)
        location = geolocator.geocode(address, country_codes=["ht", "do", "jm", "cu", "pr", "us", "ca", "fr"])
        if location is None:
            location = geolocator.geocode(address)
    except (ImportError, GeopyError, OSError) as exc:  # réseau indisponible, délai dépassé, quota, etc.
        logger.warning("Géocodage impossible pour %r : %s", address, exc)
        return None
    if location is None:
        cache.set(key, MISSING, NOT_FOUND_SECONDS)
        return None
    coords = (location.latitude, location.longitude)
    cache.set(key, coords, FOUND_SECONDS)
    return coords
