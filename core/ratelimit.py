"""Limite de requêtes par visiteur (point 01 de docs/solidite.md).

Deux niveaux :
- `RateLimitMiddleware` : plafond général par adresse IP et par minute (toutes pages, et formulaires envoyés) ;
- `@ratelimit(...)` : plafond plus serré sur les pages sensibles (connexion, inscription, paiement, contact...).

Les compteurs vivent dans le cache Django (CACHES). L'équipe EventLead connectée (rôle administrateur) n'est
jamais limitée : le jour J, plusieurs personnes pointent les invités depuis le même Wi-Fi.
"""
import logging
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

logger = logging.getLogger("eventlead.ratelimit")

SKIPPED_PREFIXES = ("/static/", "/media/", "/sante/")


def client_ip(request):
    """Adresse du visiteur. Derrière un hébergeur, l'en-tête REAL_IP_HEADER (si réglé) fait foi."""
    header = getattr(settings, "REAL_IP_HEADER", "")
    if header and request.META.get(header):
        return request.META[header].split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "inconnue"


def _is_team(request):
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated and getattr(user, "is_admin_role", False))


def hit(scope, ident, limit, window):
    """Compte une requête dans la fenêtre en cours. Renvoie True si la limite est dépassée."""
    key = f"rl:{scope}:{ident}:{int(time.time() // window)}"
    try:
        if cache.add(key, 1, window + 5):
            return 1 > limit
        try:
            return cache.incr(key) > limit
        except ValueError:  # la clé a expiré entre les deux appels
            cache.set(key, 1, window + 5)
            return 1 > limit
    except Exception:  # cache indisponible : on laisse passer plutôt que de bloquer tout le site
        logger.exception("Limite de requêtes : cache indisponible")
        return False


def too_many_response(request, retry_after):
    message = _("Trop de demandes en peu de temps. Patientez une minute puis réessayez.")
    if request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", ""):
        response = JsonResponse({"ok": False, "error": message, "message": message}, status=429)
    else:
        html = render_to_string("errors/429.html", {"message": message, "retry_after": retry_after})
        response = HttpResponse(html, status=429)
    response["Retry-After"] = str(retry_after)
    return response


class RateLimitMiddleware:
    """Plafond général : RATELIMIT_PER_MINUTE requêtes par minute et par IP, dont RATELIMIT_POSTS_PER_MINUTE envois."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.RATELIMIT_ENABLED and not request.path.startswith(SKIPPED_PREFIXES) and not _is_team(request):
            ip = client_ip(request)
            blocked = hit("all", ip, settings.RATELIMIT_PER_MINUTE, 60)
            if not blocked and request.method == "POST":
                blocked = hit("post", ip, settings.RATELIMIT_POSTS_PER_MINUTE, 60)
            if blocked:
                logger.warning("Limite générale atteinte : %s %s %s", ip, request.method, request.path)
                return too_many_response(request, 60)
        return self.get_response(request)


def ratelimit(scope, limit, window, methods=("POST",)):
    """Plafond propre à une vue : `limit` requêtes par `window` secondes et par IP, pour les méthodes données."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if settings.RATELIMIT_ENABLED and request.method in methods and not _is_team(request):
                ip = client_ip(request)
                if hit(scope, ip, limit, window):
                    logger.warning("Limite « %s » atteinte : %s %s", scope, ip, request.path)
                    return too_many_response(request, window)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
