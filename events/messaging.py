"""Messages d'invitation envoyés par WhatsApp ou par e-mail, dans la langue choisie pour chaque invité."""
from urllib.parse import quote, urlencode

from django.conf import settings
from django.utils import dateformat, translation
from django.utils.translation import gettext as _


def supported_language(code):
    return code if code in dict(settings.LANGUAGES) else settings.LANGUAGE_CODE


def invitation_url(request, guest):
    """Lien personnel de l'invité ; `lang` ouvre la page dans sa langue même si son navigateur en utilise une autre."""
    base = request.build_absolute_uri(guest.get_invitation_url())
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
