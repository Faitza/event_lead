"""Remerciements après l'événement : message des hôtes, publication, envoi aux invités présents (WhatsApp ou e-mail)."""
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from . import reminders
from .messaging import thanks_links
from .models import Event, Guest

MESSAGE_MAX = 600
MIN_GAP = timedelta(minutes=10)  # protège d'un double clic

WHATSAPP, EMAIL = Guest.Channel.WHATSAPP, Guest.Channel.EMAIL


def default_message():
    return _("Merci d'avoir partagé ce moment avec nous. Retrouvez ici les photos et ajoutez les vôtres.")


def message_for(event):
    """Le message des hôtes, ou le texte par défaut tant qu'ils n'en ont pas écrit."""
    return event.thanks_message.strip() or default_message()


def clean_message(raw):
    """Texte des hôtes : espaces nettoyés, paragraphes gardés, 600 signes au plus."""
    lines = [" ".join(line.split()) for line in str(raw or "").replace("\r", "").split("\n")]
    text = "\n".join(lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:MESSAGE_MAX]


def is_published(event):
    return event.thanks_published_at is not None


def can_view(guest):
    """Les remerciements et l'album sont réservés aux invités qui ont confirmé leur présence, une fois publiés."""
    return is_published(guest.event) and guest.status == Guest.Status.CONFIRMED


def personal_line(guest):
    """« Guerline, merci pour votre cadeau : Cafetière. » ou, pour une contribution, un merci sans montant."""
    first = guest.name.split()[0] if guest.name.split() else guest.name
    names = [claim.gift.name for claim in guest.gift_claims.select_related("gift").order_by("gift__name")]
    if names:
        return ngettext(
            "%(name)s, merci pour votre cadeau : %(gifts)s.", "%(name)s, merci pour vos cadeaux : %(gifts)s.", len(names)
        ) % {"name": first, "gifts": ", ".join(names)}
    if hasattr(guest, "contribution"):
        return _("%(name)s, merci pour votre généreuse contribution.") % {"name": first}
    return ""


def publish(event):
    event.thanks_published_at = event.thanks_published_at or timezone.now()
    event.save(update_fields=["thanks_published_at"])


def unpublish(event):
    event.thanks_published_at = None
    event.save(update_fields=["thanks_published_at"])


def present_guests(event):
    return event.guests.filter(status=Guest.Status.CONFIRMED).order_by("name")


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------

class ThanksError(Exception):
    """Le merci n'est pas parti : le message est écrit pour la personne qui administre."""


def _check(event, guest, now):
    if not is_published(event):
        raise ThanksError(_("Publiez d'abord les remerciements."))
    if guest.status != Guest.Status.CONFIRMED:
        raise ThanksError(_("%(name)s n'a pas confirmé sa présence : pas de remerciement.") % {"name": guest.name})
    if guest.thanks_sent_at and now - guest.thanks_sent_at < MIN_GAP:
        raise ThanksError(_("%(name)s vient de recevoir le remerciement.") % {"name": guest.name})
    if not reminders.effective_channel(guest):
        raise ThanksError(_("%(name)s n'a ni e-mail ni numéro WhatsApp.") % {"name": guest.name})


def send_thanks(event, guest, request=None):
    """Remercie un invité présent : e-mail envoyé par le serveur, WhatsApp noté (le message part du téléphone).

    Renvoie le canal utilisé. Lève ThanksError si le merci ne peut pas partir.
    """
    with transaction.atomic():
        guest = Guest.objects.select_for_update().select_related("event").get(pk=guest.pk, event=event)
        now = timezone.now()
        _check(event, guest, now)
        channel = reminders.effective_channel(guest)
        if channel == EMAIL:
            links = thanks_links(request, guest)
            try:
                EmailMessage(
                    links["subject"], links["body"], settings.DEFAULT_FROM_EMAIL, [guest.email],
                    reply_to=[settings.CONTACT_EMAIL],
                ).send(fail_silently=False)
            except Exception as exc:  # SMTP absent, refusé, etc. : rien n'est enregistré
                raise ThanksError(_("L'e-mail à %(name)s n'a pas pu partir. Réessayez plus tard.") % {"name": guest.name}) from exc
        guest.thanks_sent_at = now
        guest.save(update_fields=["thanks_sent_at"])
    return channel


def send_all_emails(event, request=None):
    """Envoie le merci par e-mail aux invités présents qui ne l'ont pas encore reçu. Les WhatsApp restent à envoyer un par un."""
    result = {"sent": 0, "failed": 0, "whatsapp_waiting": 0}
    if not is_published(event):
        return result
    for guest in present_guests(event).filter(thanks_sent_at__isnull=True):
        channel = reminders.effective_channel(guest)
        if channel == WHATSAPP:
            result["whatsapp_waiting"] += 1
        elif channel == EMAIL:
            try:
                send_thanks(event, guest, request)
            except ThanksError:
                result["failed"] += 1
            else:
                result["sent"] += 1
    return result
