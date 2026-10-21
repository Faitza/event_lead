import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .ratelimit import client_ip, ratelimit

logger = logging.getLogger("eventlead")


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def bad_request(request, exception=None):
    """Requête refusée (formulaire trop lourd, en-tête invalide...) : page autonome, sans base de données."""
    return HttpResponseBadRequest(render_to_string("errors/400.html"))


def server_error(request):
    """Le site a planté : message clair au lieu d'une page blanche. L'erreur est déjà dans le journal (django.request)."""
    try:
        html = render_to_string("errors/500.html", {"contact_whatsapp": settings.CONTACT_WHATSAPP})
    except Exception:  # même le gabarit a échoué : texte brut
        logger.exception("Page d'erreur 500 impossible à afficher")
        html = "<h1>EventLead</h1><p>Un problème est survenu. Réessayez dans un instant.</p>"
    return HttpResponseServerError(html)


def health(request):
    """17. Adresse surveillée par un service d'alerte (UptimeRobot...) : 200 si la base et le cache répondent, sinon 503."""
    from django.core.cache import cache
    from django.db import connection

    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["base"] = "ok"
    except Exception:
        logger.exception("Santé : base de données injoignable")
        checks["base"] = "erreur"
    try:
        cache.set("sante", 1, 10)
        checks["cache"] = "ok" if cache.get("sante") == 1 else "erreur"
    except Exception:
        logger.exception("Santé : cache injoignable")
        checks["cache"] = "erreur"
    ok = all(v == "ok" for v in checks.values())
    body = ("ok" if ok else "erreur") + "".join(f"\n{k}: {v}" for k, v in checks.items())
    response = HttpResponse(body, content_type="text/plain; charset=utf-8", status=200 if ok else 503)
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt  # envoyé par navigator.sendBeacon, sans jeton ; il ne fait qu'écrire une ligne dans le journal
@require_POST
@ratelimit("browser-error", 10, 60)
def browser_error(request):
    """18. Erreur JavaScript chez un visiteur : une ligne dans le journal (texte tronqué, jamais affiché)."""
    raw = request.body[:2000].decode("utf-8", "replace")
    logging.getLogger("eventlead.browser").warning("Erreur navigateur (%s) : %s", client_ip(request), " ".join(raw.split()))
    return HttpResponse(status=204)
