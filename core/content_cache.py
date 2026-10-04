"""Contenu qui change rarement, gardé en mémoire (point 16 de docs/solidite.md).

L'accueil et le menu relisent à chaque visite les mêmes catégories, événements publics, publicités et avis.
Ils sont gardés CONTENT_CACHE_SECONDS secondes (5 minutes par défaut) puis relus. Dès qu'un événement,
une catégorie, une publicité ou un avis est enregistré ou supprimé, tout ce contenu est oublié d'un coup
(numéro de version), donc une modification se voit tout de suite.
"""
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import get_language

VERSION_KEY = "content:version"


def remember(name, builder):
    """Valeur de `builder()`, relue au plus toutes les CONTENT_CACHE_SECONDS secondes, par langue et par jour."""
    seconds = settings.CONTENT_CACHE_SECONDS
    if not seconds:
        return builder()
    try:
        version = cache.get_or_set(VERSION_KEY, 1, None)
        key = f"content:{version}:{name}:{get_language()}:{timezone.localdate():%Y%m%d}"
        stored = cache.get(key)
        if stored is not None:
            return stored[0]
    except Exception:  # cache indisponible : on lit simplement la base
        return builder()
    value = builder()
    try:
        cache.set(key, (value,), seconds)  # tuple : une valeur None est aussi gardée
    except Exception:
        pass
    return value


def forget(**kwargs):
    """Tout le contenu gardé devient périmé (appelé à chaque enregistrement d'un modèle concerné)."""
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 2, None)
    except Exception:
        pass
