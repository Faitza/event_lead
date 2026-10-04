"""Relances des invités sans réponse : qui relancer, quand, envoi par e-mail, journal. Jamais de SMS."""
from dataclasses import dataclass
from datetime import time, timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core import quotas

from .messaging import reminder_links
from .models import Event, Guest, Reminder

FIRST_AFTER_CHOICES = (3, 7, 14)
EVERY_CHOICES = (3, 7, 14)
MAX_CHOICES = (1, 2, 3)
HOUR_CHOICES = tuple(range(7, 21))
ABSOLUTE_MAX = 3  # jamais plus de 3 relances par invité, même à la main
MIN_GAP = timedelta(minutes=10)  # protège d'un double clic

WHATSAPP, EMAIL = Guest.Channel.WHATSAPP, Guest.Channel.EMAIL

# États d'une ligne
DUE, WAITING, MAXED, NOT_INVITED, NO_CONTACT = "due", "waiting", "maxed", "not_invited", "no_contact"
SENT, SKIPPED, FAILED = "sent", "skipped", "failed"


@dataclass
class Row:
    guest: Guest
    count: int
    last_at: object
    channel: str  # canal réellement utilisé pour cette relance ; "" s'il n'y a aucun contact
    due_on: object  # jour prévu de la prochaine relance
    state: str

    @property
    def can_remind(self):
        return self.state in (DUE, WAITING)

    @property
    def is_due(self):
        return self.state == DUE

    @property
    def is_never(self):
        return self.count == 0


def event_accepts_reminders(event):
    return event.status == Event.Status.ACTIVE and not event.is_past


def effective_channel(guest):
    """Même canal que l'invitation ; si le contact manque, l'autre canal ; sinon aucun."""
    if guest.sent_via == EMAIL and guest.email:
        return EMAIL
    if guest.phone and "".join(c for c in guest.phone if c.isdigit()):
        return WHATSAPP
    if guest.email:
        return EMAIL
    return ""


def limit_for(event):
    return max(0, min(event.reminder_max, ABSOLUTE_MAX))


def _due_on(event, guest, count, last_at):
    if count == 0:
        return timezone.localtime(guest.invitation_sent_at).date() + timedelta(days=event.reminder_first_after_days)
    return timezone.localtime(last_at).date() + timedelta(days=event.reminder_every_days)


def _row(event, guest, count, last_at, today):
    channel = effective_channel(guest)
    if not guest.invitation_sent_at:
        return Row(guest, count, last_at, channel, None, NOT_INVITED)
    due_on = _due_on(event, guest, count, last_at)
    if count >= limit_for(event):
        state = MAXED
    elif not channel:
        state = NO_CONTACT
    else:
        state = DUE if due_on <= today else WAITING
    return Row(guest, count, last_at, channel, due_on, state)


def overview(event):
    """Une ligne par invité sans réponse (les invités qui ont répondu ne sont jamais relancés)."""
    today = timezone.localdate()
    guests = list(event.guests.filter(status=Guest.Status.PENDING).order_by("name"))
    history = {}
    for guest_id, sent_at in Reminder.objects.filter(guest__in=guests).order_by("sent_at").values_list("guest_id", "sent_at"):
        count, _last = history.get(guest_id, (0, None))
        history[guest_id] = (count + 1, sent_at)
    return [_row(event, g, *history.get(g.pk, (0, None)), today) for g in guests]


def stats(event, rows):
    invited = [r for r in rows if r.state != NOT_INVITED]
    reminded = [r for r in invited if r.count]
    upcoming = [r.due_on for r in invited if r.state in (DUE, WAITING)]
    return {
        "total": event.guests.count(),
        "no_reply": len(rows),
        "invited": len(invited),
        "not_invited": len(rows) - len(invited),
        "never": sum(1 for r in invited if not r.count),
        "reminded": len(reminded),
        "once": sum(1 for r in reminded if r.count == 1),
        "twice": sum(1 for r in reminded if r.count == 2),
        "thrice": sum(1 for r in reminded if r.count >= 3),
        "due": sum(1 for r in invited if r.is_due),
        "due_email": sum(1 for r in invited if r.is_due and r.channel == EMAIL),
        "due_whatsapp": sum(1 for r in invited if r.is_due and r.channel == WHATSAPP),
        "next_on": min(upcoming) if upcoming else None,
        "maxed": sum(1 for r in invited if r.state == MAXED),
        "no_contact": sum(1 for r in invited if r.state == NO_CONTACT),
    }


FILTERS = ("never", "1", "2", "3", "due")


def filter_rows(rows, name):
    if name == "never":
        return [r for r in rows if r.state != NOT_INVITED and r.count == 0]
    if name == "due":
        return [r for r in rows if r.is_due]
    if name in ("1", "2", "3"):
        n = int(name)
        return [r for r in rows if r.count == n or (n == 3 and r.count > 3)]
    return rows


def email_demo_mode():
    """Vrai tant que les e-mails ne partent pas vraiment (affichés dans la console du serveur ou gardés en mémoire)."""
    return settings.EMAIL_BACKEND.rsplit(".", 2)[-2] in ("console", "locmem", "dummy", "filebased")


# ---------------------------------------------------------------------------
# Envoi et journal
# ---------------------------------------------------------------------------

class ReminderError(Exception):
    """La relance n'est pas partie : le message est écrit pour la personne qui administre."""


def _check(event, guest, now):
    """Refuse une relance qui n'a plus lieu d'être. Appelé avec l'invité verrouillé."""
    if not event_accepts_reminders(event):
        raise ReminderError(_("Cet événement n'accepte plus de relances."))
    if guest.status != Guest.Status.PENDING:
        raise ReminderError(_("%(name)s a déjà répondu : plus de relance.") % {"name": guest.name})
    if not guest.invitation_sent_at:
        raise ReminderError(_("L'invitation de %(name)s n'est pas encore envoyée.") % {"name": guest.name})
    existing = list(guest.reminders.order_by("-sent_at"))
    if len(existing) >= limit_for(event):
        raise ReminderError(_("%(name)s a déjà reçu le maximum de relances.") % {"name": guest.name})
    if existing and now - existing[0].sent_at < MIN_GAP:
        raise ReminderError(_("%(name)s vient d'être relancé(e).") % {"name": guest.name})
    if not effective_channel(guest):
        raise ReminderError(_("%(name)s n'a ni e-mail ni numéro WhatsApp.") % {"name": guest.name})


def _send_email(request, guest):
    links = reminder_links(request, guest)
    message = EmailMessage(
        links["subject"], links["body"], settings.DEFAULT_FROM_EMAIL, [guest.email], reply_to=[settings.CONTACT_EMAIL],
    )
    quotas.send_email(message)


def remind_guest(event, guest, user=None, request=None, automatic=False):
    """Relance un invité : e-mail envoyé par le serveur, WhatsApp enregistré (le message est envoyé depuis le téléphone).

    Renvoie le canal utilisé. Lève ReminderError si la relance n'est plus permise ou si l'envoi échoue.
    """
    with transaction.atomic():
        guest = Guest.objects.select_for_update().select_related("event").get(pk=guest.pk, event=event)
        now = timezone.now()
        _check(event, guest, now)
        channel = effective_channel(guest)
        if channel == EMAIL:
            try:
                _send_email(request, guest)
            except quotas.QuotaExceeded as exc:
                raise ReminderError(_("Plafond d'e-mails du jour atteint : la relance de %(name)s partira demain.") % {"name": guest.name}) from exc
            except Exception as exc:  # SMTP absent, refusé, etc. : rien n'est enregistré
                raise ReminderError(_("L'e-mail à %(name)s n'a pas pu partir. Réessayez plus tard.") % {"name": guest.name}) from exc
        Reminder.objects.create(guest=guest, channel=channel, automatic=automatic, sent_by=user, sent_at=now)
    return channel


def send_due_emails(event, user=None, request=None, automatic=False):
    """Envoie les relances par e-mail arrivées à échéance. Les WhatsApp ne peuvent partir que depuis le téléphone."""
    result = {SENT: 0, FAILED: 0, SKIPPED: 0, "whatsapp_waiting": 0}
    if not event_accepts_reminders(event):
        return result
    for row in overview(event):
        if not row.is_due:
            continue
        if row.channel != EMAIL:
            result["whatsapp_waiting"] += 1
            continue
        try:
            remind_guest(event, row.guest, user, request, automatic)
        except ReminderError:
            result[FAILED] += 1
        else:
            result[SENT] += 1
    return result


def reminder_time(event):
    return time(min(max(event.reminder_hour, 0), 23), 0)


def validate_settings(data):
    """Réglages envoyés par la page : renvoie (valeurs, erreur)."""
    try:
        values = {
            "reminder_first_after_days": int(data.get("first_after", "")),
            "reminder_every_days": int(data.get("every", "")),
            "reminder_max": int(data.get("max", "")),
            "reminder_hour": int(data.get("hour", "")),
        }
    except (TypeError, ValueError):
        return None, _("Réglages invalides.")
    if (
        values["reminder_first_after_days"] not in FIRST_AFTER_CHOICES
        or values["reminder_every_days"] not in EVERY_CHOICES
        or values["reminder_max"] not in MAX_CHOICES
        or values["reminder_hour"] not in HOUR_CHOICES
    ):
        return None, _("Réglages invalides.")
    values["reminders_auto"] = data.get("auto") in ("on", "1", "true")
    return values, None
