from django.conf import settings
from django.utils import timezone

from events.models import Event

from .content_cache import remember
from .models import HelpRequest


def _next_public_event():
    return remember("next-public-event", lambda: Event.objects.public_active().upcoming().first())


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
        "TODAY": timezone.localdate,
        # (code, sigle affiché, nom dans sa propre langue) : jamais traduits
        "LANGUAGE_OPTIONS": [("fr", "FR", "Français"), ("en", "EN", "English"), ("ht", "KR", "Kreyòl ayisyen")],
    }
