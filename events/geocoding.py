"""Géocodage adresse vers coordonnées avec geopy + Nominatim (OpenStreetMap, gratuit)."""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def geocode_address(address):
    """Retourne (latitude, longitude) ou None si l'adresse est introuvable ou le service indisponible."""
    if not address:
        return None
    try:
        from geopy.exc import GeopyError
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent=settings.GEOCODER_USER_AGENT, timeout=5)
        location = geolocator.geocode(address, country_codes=["ht", "do", "jm", "cu", "pr", "us", "ca", "fr"])
        if location is None:
            location = geolocator.geocode(address)
    except (ImportError, GeopyError, OSError) as exc:  # réseau indisponible, quota, etc.
        logger.warning("Géocodage impossible pour %r : %s", address, exc)
        return None
    if location is None:
        return None
    return location.latitude, location.longitude
