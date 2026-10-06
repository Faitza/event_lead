from django.conf import settings
from django.templatetags.static import static
from django.utils import timezone

from events.models import Event

from .content_cache import remember
from .models import HelpRequest, LogoVariant


def _next_public_event():
    return remember("next-public-event", lambda: Event.objects.public_active().upcoming().first())


def _site_logo():
    """Logo du jour : la version prévue pour aujourd'hui (Tableau de bord > Logo), sinon l'original."""
    def build():
        variant = LogoVariant.current()
        if variant:
            light, dark = variant.urls
        else:
            light, dark = static("img/logo/eventlead-original.png"), static("img/logo/eventlead-original-sombre.png")
        return {"light": light, "dark": dark}
    return remember("site-logo", build)


# Pages qui ne doivent pas apparaître dans Google : espaces personnels, tableau de bord, invitations (lien secret),
# paiements, formulaires. Les mêmes chemins sont interdits dans /robots.txt (core/seo.py).
PRIVATE_PREFIXES = (
    "/admin-dashboard/", "/django-admin/", "/accounts/", "/connexion/", "/inscription/", "/deconnexion/",
    "/tableau-de-bord/", "/devenir-organisateur/", "/mon-espace/", "/mon-profil/", "/organisateur/",
    "/invitation/", "/entree/", "/paiement/", "/publicites/", "/recherche/", "/langue/", "/journal/",
    "/avis/", "/contact/",
)
OG_LOCALES = {"fr": "fr_FR", "en": "en_US", "ht": "ht_HT"}


def _is_private(path):
    return path.startswith(PRIVATE_PREFIXES) or ("/billetterie/" in path and path.endswith("/payer/"))


def _new_help_requests():
    return HelpRequest.objects.filter(status=HelpRequest.Status.NEW).count()


def site_settings(request):
    return {
        "CONTACT_EMAIL": settings.CONTACT_EMAIL,
        "CONTACT_PHONE": settings.CONTACT_PHONE,
        "CONTACT_WHATSAPP": settings.CONTACT_WHATSAPP,
        "CONTACT_ADDRESS": settings.CONTACT_ADDRESS,
        "GOOGLE_LOGIN_ENABLED": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "PAYMENT_DEMO_MODE": settings.PAYMENT_DEMO_MODE,
        # Appelable : la requête n'est exécutée que si le gabarit l'utilise.
        "next_public_event": _next_public_event,
        "new_help_requests": _new_help_requests,
        "site_logo": _site_logo,
        "TODAY": timezone.localdate,
        # Adresse du site vue par le visiteur (https://... en ligne), pour les liens complets des réseaux sociaux
        "SITE_ORIGIN": f"{request.scheme}://{request.get_host()}",
        "OG_LOCALE": OG_LOCALES.get((getattr(request, "LANGUAGE_CODE", "") or "fr")[:2], "fr_FR"),
        "robots_noindex": _is_private(request.path),
        # (code, sigle affiché, nom dans sa propre langue) : jamais traduits
        "LANGUAGE_OPTIONS": [("fr", "FR", "Français"), ("en", "EN", "English"), ("ht", "KR", "Kreyòl ayisyen")],
    }
