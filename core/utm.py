"""Suivi des liens de campagne (utm_source, utm_medium, utm_campaign, utm_term, utm_content), sans outil extérieur.

1. Un visiteur arrive par un lien qui porte des paramètres utm_* : ils sont gardés dans sa session (le dernier lien
   suivi remplace le précédent).
2. S'il s'inscrit, paie, demande de l'aide ou écrit à l'équipe, `record()` enregistre une ligne `Attribution`.
3. Le tableau de bord (Provenance des visites) compte ces lignes par source et par campagne.
"""
from django.utils import timezone

from .models import Attribution

FIELDS = ("source", "medium", "campaign", "term", "content")
SESSION_KEY = "utm"
MAX_LEN = 120


class UtmCaptureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and hasattr(request, "session"):
            found = {f: request.GET.get(f"utm_{f}", "").strip()[:MAX_LEN] for f in FIELDS}
            if any(found.values()):
                found["landing_page"] = request.path[:300]
                found["seen_at"] = timezone.now().isoformat(timespec="seconds")
                request.session[SESSION_KEY] = found
        return self.get_response(request)


def current(request):
    """Paramètres utm_* gardés pour ce visiteur, ou None."""
    data = getattr(request, "session", None) and request.session.get(SESSION_KEY)
    return data if isinstance(data, dict) else None


def record(request, kind, label="", user=None):
    """Note la provenance de l'action si le visiteur est arrivé par un lien de campagne. Ne bloque jamais l'action."""
    data = current(request)
    if not data:
        return None
    if user is None and getattr(request, "user", None) is not None and request.user.is_authenticated:
        user = request.user
    try:
        return Attribution.objects.create(
            kind=kind, label=str(label)[:200], user=user, landing_page=str(data.get("landing_page", ""))[:300],
            **{f: str(data.get(f, ""))[:MAX_LEN] for f in FIELDS},
        )
    except Exception:  # noqa: BLE001 - le suivi ne doit jamais faire échouer une inscription ou un paiement
        return None


def record_signup(sender, request=None, user=None, **kwargs):
    """Signal d'allauth (inscription avec Google)."""
    if request is not None and user is not None:
        record(request, Attribution.Kind.SIGNUP, user.email, user=user)
