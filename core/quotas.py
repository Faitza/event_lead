"""Plafonds d'appels aux services extérieurs (point 02 de docs/solidite.md).

Chaque service a un nombre maximum d'appels par jour pour tout le site (réglages GEOCODER_DAILY_LIMIT,
EMAIL_DAILY_LIMIT). Au-delà, l'appel n'est pas fait : l'écran le dit, et le journal garde une trace.
Cela protège d'une boucle qui s'emballe, d'un abus, et des frais d'un fournisseur payant au volume.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("eventlead.quotas")


class QuotaExceeded(Exception):
    """Le plafond du jour est atteint : l'appel n'a pas été fait."""


def _key(name):
    return f"quota:{name}:{timezone.localdate():%Y%m%d}"


def used(name):
    return cache.get(_key(name), 0)


def take(name, daily_limit):
    """Réserve un appel au service `name`. Lève QuotaExceeded si le plafond du jour est atteint."""
    key = _key(name)
    try:
        cache.add(key, 0, 60 * 60 * 26)
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 60 * 60 * 26)
        count = 1
    if count > daily_limit:
        if count == daily_limit + 1:  # une seule alerte par jour et par service
            logger.error("Plafond du jour atteint pour %s (%d appels) : les appels suivants sont bloqués jusqu'à minuit.", name, daily_limit)
        raise QuotaExceeded(name)


def send_email(message):
    """Envoie un EmailMessage en respectant EMAIL_DAILY_LIMIT. Lève QuotaExceeded ou l'erreur du serveur d'e-mail."""
    take("email", settings.EMAIL_DAILY_LIMIT)
    return message.send(fail_silently=False)
