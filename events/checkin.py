"""Pointage à l'entrée le jour J : lecture du QR code, recherche manuelle, ajout sur place, annulation."""
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils import dateformat, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import CheckIn, Guest, normalize_entry_code

Result = CheckIn.Result


@dataclass
class Outcome:
    result: str
    guest: Guest = None
    check_in: CheckIn = None
    first_at: object = None  # heure du premier passage, pour un QR déjà utilisé
    other_event: object = None  # événement du billet, pour un QR d'un autre événement

    @property
    def accepted(self):
        return self.result in (Result.VALIDATED, Result.WALK_IN)


def _log(event, guest, code, result, source, user):
    return CheckIn.objects.create(event=event, guest=guest, code=code, result=result, source=source, scanned_by=user)


def check_in_guest(event, guest, user, source=CheckIn.Source.QR, code=""):
    """Pointe un invité de l'événement ; un second passage est refusé (QR déjà utilisé)."""
    with transaction.atomic():
        guest = Guest.objects.select_for_update().get(pk=guest.pk)
        if guest.checked_in_at:
            entry = _log(event, guest, code or guest.entry_code, Result.DUPLICATE, source, user)
            return Outcome(Result.DUPLICATE, guest, entry, first_at=guest.checked_in_at)
        guest.checked_in_at = timezone.now()
        guest.save(update_fields=["checked_in_at"])
        entry = _log(event, guest, code or guest.entry_code, Result.VALIDATED, source, user)
    return Outcome(Result.VALIDATED, guest, entry)


def scan(event, raw_code, user):
    """Lecture d'un QR code : valide, déjà utilisé, inconnu ou d'un autre événement."""
    raw = (raw_code or "").strip()
    # Le QR contient l'adresse /entree/<code>/ : on garde la dernière partie de l'adresse
    if "/" in raw:
        raw = [part for part in raw.split("?")[0].split("/") if part][-1]
    code = normalize_entry_code(raw)
    guest = Guest.objects.select_related("event").filter(entry_code=code).first()
    if guest is None:
        return Outcome(Result.UNKNOWN, check_in=_log(event, None, code[:60], Result.UNKNOWN, CheckIn.Source.QR, user))
    if guest.event_id != event.pk:
        entry = _log(event, None, code, Result.WRONG_EVENT, CheckIn.Source.QR, user)
        return Outcome(Result.WRONG_EVENT, check_in=entry, other_event=guest.event)
    return check_in_guest(event, guest, user, CheckIn.Source.QR, code)


def add_walk_in(event, name, companions, phone, user):
    """Invité arrivé sans être sur la liste : créé comme présent et pointé tout de suite (hors limite d'invités)."""
    now = timezone.now()
    guest = Guest.objects.create(
        event=event, name=name, phone=phone, companions=companions, status=Guest.Status.CONFIRMED,
        replied_at=now, checked_in_at=now, added_on_site=True,
    )
    entry = _log(event, guest, guest.entry_code, Result.WALK_IN, CheckIn.Source.WALK_IN, user)
    return Outcome(Result.WALK_IN, guest, entry)


def cancel_check_in(event, guest, user):
    """Annule un pointage fait par erreur : l'invité redevient « attendu »."""
    with transaction.atomic():
        guest = Guest.objects.select_for_update().get(pk=guest.pk, event=event)
        if not guest.checked_in_at:
            return None
        guest.checked_in_at = None
        guest.save(update_fields=["checked_in_at"])
        return _log(event, guest, guest.entry_code, Result.CANCELLED, CheckIn.Source.MANUAL, user)


def search_guests(event, query, limit=8):
    query = (query or "").strip()
    if len(query) < 2:
        return []
    guests = event.guests.filter(Q(name__icontains=query) | Q(entry_code__icontains=normalize_entry_code(query)))
    return list(guests.order_by("name")[:limit])


def stats(event):
    guests = event.guests
    confirmed = guests.filter(status=Guest.Status.CONFIRMED).count()
    arrived = guests.filter(checked_in_at__isnull=False)
    arrived_count = arrived.count()
    companions = sum(arrived.values_list("companions", flat=True))
    expected = guests.filter(status=Guest.Status.CONFIRMED, checked_in_at__isnull=True).count()
    return {
        "confirmed": confirmed,
        "arrived": arrived_count,
        "people": arrived_count + companions,
        "expected": expected,
        "refused": event.check_ins.filter(result__in=CheckIn.REFUSED).count(),
        "on_site": arrived.filter(added_on_site=True).count(),
        "percent": min(100, round(arrived_count * 100 / confirmed)) if confirmed else 0,
    }


# ---------------------------------------------------------------------------
# Texte du résultat, dans la langue de la personne qui pointe
# ---------------------------------------------------------------------------

TONES = {
    Result.VALIDATED: "success",
    Result.WALK_IN: "success",
    Result.DUPLICATE: "warning",
    Result.UNKNOWN: "danger",
    Result.WRONG_EVENT: "danger",
    Result.CANCELLED: "muted",
}


def clock(moment):
    return dateformat.format(timezone.localtime(moment), _("H\\hi"))


def party_text(guest):
    if guest.companions:
        return ngettext(
            "%(n)d personnes (avec %(c)d accompagnant)", "%(n)d personnes (avec %(c)d accompagnants)", guest.companions,
        ) % {"n": guest.party_size, "c": guest.companions}
    return _("1 personne")


def describe(outcome):
    """Texte du résultat pour l'écran de pointage : titre, nom, détail, remarque."""
    guest, result = outcome.guest, outcome.result
    title = dict(Result.choices)[result]
    name = guest.name if guest else ""
    note = ""
    if result in (Result.VALIDATED, Result.WALK_IN):
        detail = party_text(guest)
        if guest.status != Guest.Status.CONFIRMED:
            note = _("Réponse de l'invité : %(status)s.") % {"status": guest.get_status_display()}
    elif result == Result.DUPLICATE:
        detail = _("Déjà pointé à %(time)s.") % {"time": clock(outcome.first_at)}
    elif result == Result.WRONG_EVENT:
        detail = _("Ce billet est pour « %(title)s ».") % {"title": outcome.other_event.title}
    else:
        detail = _("Ce code ne correspond à aucun invité.")
    return {
        "result": result,
        "tone": TONES[result],
        "title": str(title),
        "name": name,
        "detail": detail,
        "note": note,
        "table": guest.table.label if guest is not None and guest.table_id and result in (Result.VALIDATED, Result.DUPLICATE) else "",
        "time": clock(outcome.check_in.created_at) if outcome.check_in else "",
    }
