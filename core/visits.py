"""Compteur de visites privé : combien de fois chaque page a été vue, jour par jour.

Rien n'est envoyé à un service extérieur, aucun cookie n'est posé, aucune adresse IP n'est gardée : une ligne
par jour et par page avec un nombre. La page est désignée par son nom dans le site (ex. « events:public_detail »),
jamais par son adresse : les liens secrets des invitations ne sont donc jamais enregistrés.
Ne sont pas comptés : les robots (Google, aperçus WhatsApp et Facebook...), l'équipe connectée, le tableau de bord,
les erreurs et les redirections.
"""
import logging
import re

from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import PageView

logger = logging.getLogger("eventlead")

BOT_RE = re.compile(r"bot|crawl|spider|slurp|facebookexternalhit|whatsapp|telegram|preview|curl|wget|python|headless|monitor|lighthouse", re.I)
SKIPPED_NAMESPACES = {"dashboard", "admin"}

# Noms lisibles des pages dans le tableau de bord (les autres gardent leur nom technique)
LABELS = {
    "core:landing": _("Accueil"),
    "events:explore": _("Événements"),
    "events:public_detail": _("Fiche d'un événement"),
    "payments:ticketing": _("Billetterie"),
    "payments:checkout": _("Achat d'un billet"),
    "core:help": _("Aide"),
    "core:search": _("Recherche"),
    "core:privacy": _("Confidentialité"),
    "core:terms": _("Conditions d'utilisation"),
    "accounts:login": _("Connexion"),
    "accounts:register": _("Inscription"),
    "accounts:register_organizer": _("Inscription organisateur"),
    "accounts:guest_space": _("Mon espace"),
    "events:invitation": _("Invitation ouverte"),
    "events:invitation_done": _("Réponse envoyée"),
    "events:invitation_ticket": _("Billet d'entrée"),
    "events:invitation_thanks": _("Remerciements et album"),
}


def should_count(request, response):
    if request.method != "GET" or response.status_code != 200:
        return None
    if not response.get("Content-Type", "").startswith("text/html"):
        return None
    match = getattr(request, "resolver_match", None)
    if match is None or not match.view_name or set(match.namespaces) & SKIPPED_NAMESPACES:
        return None
    if request.path.startswith(("/django-admin/", "/admin-dashboard/")):
        return None
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and (user.is_staff or getattr(user, "is_admin_role", False)):
        return None
    if BOT_RE.search(request.META.get("HTTP_USER_AGENT", "")) or not request.META.get("HTTP_USER_AGENT"):
        return None
    return match.view_name[:80]


def count(page):
    day = timezone.localdate()
    try:
        updated = PageView.objects.filter(day=day, page=page).update(views=F("views") + 1)
        if not updated:
            _, created = PageView.objects.get_or_create(day=day, page=page, defaults={"views": 1})
            if not created:
                PageView.objects.filter(day=day, page=page).update(views=F("views") + 1)
    except Exception:  # noqa: BLE001 - le compteur ne doit jamais faire échouer une page
        logger.warning("Compteur de visites indisponible", exc_info=True)


class PageViewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        page = should_count(request, response)
        if page:
            count(page)
        return response


def summary(days=30):
    """Pour le tableau de bord : vues par page sur `days` jours, et total par jour sur 14 jours."""
    from django.db.models import Sum

    today = timezone.localdate()
    since = today - timezone.timedelta(days=days - 1)
    pages = [
        {"page": row["page"], "label": LABELS.get(row["page"], row["page"]), "views": row["n"]}
        for row in PageView.objects.filter(day__gte=since).values("page").annotate(n=Sum("views")).order_by("-n")
    ]
    per_day = dict(PageView.objects.filter(day__gte=today - timezone.timedelta(days=13))
                   .values_list("day").annotate(n=Sum("views")))
    daily = [(today - timezone.timedelta(days=i), per_day.get(today - timezone.timedelta(days=i), 0)) for i in range(13, -1, -1)]
    peak = max([n for _, n in daily] + [1])
    return {
        "pages": pages, "total": sum(p["views"] for p in pages), "today": per_day.get(today, 0), "days": days,
        "daily": [{"day": d, "views": n, "pct": round(100 * n / peak)} for d, n in daily],
    }
