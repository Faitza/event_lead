"""Messages d'invitation envoyés par WhatsApp ou par e-mail, dans la langue choisie pour chaque invité."""
from urllib.parse import quote, urlencode

from django.conf import settings
from django.utils import dateformat, translation
from django.utils.translation import gettext as _


def supported_language(code):
    return code if code in dict(settings.LANGUAGES) else settings.LANGUAGE_CODE


def absolute_url(request, path):
    """Adresse complète ; sans requête (commande planifiée), on part de SITE_URL."""
    if request is not None:
        return request.build_absolute_uri(path)
    return settings.SITE_URL.rstrip("/") + path


def invitation_url(request, guest):
    """Lien personnel de l'invité ; `lang` ouvre la page dans sa langue même si son navigateur en utilise une autre."""
    base = absolute_url(request, guest.get_invitation_url())
    return f"{base}?{urlencode({'lang': supported_language(guest.language)})}"


def invitation_texts(request, guest):
    """(objet, texte) de l'invitation, écrits dans la langue de l'invité."""
    url = invitation_url(request, guest)
    event = guest.event
    with translation.override(supported_language(guest.language)):
        subject = _("Invitation : %(title)s") % {"title": event.title}
        body = _(
            "Bonjour %(name)s, vous êtes invité(e) à « %(title)s » le %(date)s à %(time)s. "
            "Merci de confirmer votre présence ici : %(url)s"
        ) % {
            "name": guest.name,
            "title": event.title,
            "date": dateformat.format(event.date, _("d/m/Y")),
            "time": dateformat.format(event.time, "H:i"),
            "url": url,
        }
    return url, subject, body


def invitation_links(request, guest):
    """Liens prêts à envoyer : lien personnel, WhatsApp et e-mail avec le message déjà écrit."""
    url, subject, body = invitation_texts(request, guest)
    phone = "".join(c for c in guest.phone if c.isdigit())
    return {
        "url": url,
        "whatsapp": f"https://wa.me/{phone}?text={quote(body)}" if phone else f"https://wa.me/?text={quote(body)}",
        "mailto": f"mailto:{guest.email}?subject={quote(subject)}&body={quote(body)}",
    }


def reminder_texts(request, guest):
    """(lien, objet, texte) de la relance, dans la langue de l'invité : même lien personnel, sans connexion."""
    url = invitation_url(request, guest)
    event = guest.event
    with translation.override(supported_language(guest.language)):
        subject = _("Rappel : %(title)s") % {"title": event.title}
        body = _(
            "Bonjour %(name)s, les hôtes de « %(title)s » attendent encore votre réponse. "
            "L'événement a lieu le %(date)s à %(time)s.\n\n"
            "Répondez en quelques secondes :\n%(url)s\n\n"
            "Le lien ouvre la page de réponse, sans connexion."
        ) % {
            "name": guest.name,
            "title": event.title,
            "date": dateformat.format(event.date, _("l j F Y")),
            "time": dateformat.format(event.time, "H:i"),
            "url": url,
        }
    return url, subject, body


def reminder_links(request, guest):
    """Liens de la relance : WhatsApp avec le message déjà écrit, ou e-mail (jamais de SMS)."""
    url, subject, body = reminder_texts(request, guest)
    phone = "".join(c for c in guest.phone if c.isdigit())
    return {
        "url": url,
        "subject": subject,
        "body": body,
        "whatsapp": f"https://wa.me/{phone}?text={quote(body)}" if phone else f"https://wa.me/?text={quote(body)}",
    }
