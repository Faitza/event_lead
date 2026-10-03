"""Plan de table : tables, places, placement des invités avec leurs accompagnants, placement automatique."""
from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import Event, Guest, Table

DEFAULT_TABLES = 12
DEFAULT_CAPACITY = 12
MAX_TABLES = 100


class SeatingError(Exception):
    """Un changement refusé : le message est écrit pour la personne qui administre."""


@dataclass
class TableView:
    table: Table
    guests: list = field(default_factory=list)

    @property
    def taken(self):
        return sum(g.party_size for g in self.guests)

    @property
    def free(self):
        return max(self.table.capacity - self.taken, 0)

    @property
    def full(self):
        return self.taken >= self.table.capacity

    @property
    def percent(self):
        return min(100, round(self.taken * 100 / self.table.capacity)) if self.table.capacity else 0


def seatable_guests(event):
    """Les invités à placer : ceux qui ont confirmé leur présence."""
    return event.guests.filter(status=Guest.Status.CONFIRMED)


def board(event):
    """Tables avec leurs invités, invités sans table et chiffres."""
    tables = list(event.tables.all())
    views = {t.pk: TableView(t) for t in tables}
    unseated = []
    for guest in seatable_guests(event).order_by("name"):
        if guest.table_id in views:
            views[guest.table_id].guests.append(guest)
        else:
            unseated.append(guest)
    ordered = [views[t.pk] for t in tables]
    seats = sum(t.capacity for t in tables)
    placed = sum(v.taken for v in ordered)
    return {
        "tables": ordered,
        "unseated": unseated,
        "stats": {
            "tables": len(tables),
            "capacity_min": min((t.capacity for t in tables), default=0),
            "capacity_max": max((t.capacity for t in tables), default=0),
            "seats": seats,
            "free": max(seats - placed, 0),
            "placed": placed,
            "placed_guests": sum(len(v.guests) for v in ordered),
            "unseated": len(unseated),
            "unseated_people": sum(g.party_size for g in unseated),
            "over": placed > seats,
        },
    }


def _locked_table(event, table_id):
    try:
        return Table.objects.select_for_update().get(pk=table_id, event=event)
    except (Table.DoesNotExist, ValueError, TypeError):
        raise SeatingError(_("Cette table n'existe plus."))


def _taken(table, excluding=None):
    guests = table.guests.filter(status=Guest.Status.CONFIRMED)
    if excluding is not None:
        guests = guests.exclude(pk=excluding)
    return sum(g.party_size for g in guests)


def seat_guest(event, guest_id, table_id):
    """Place un invité (avec ses accompagnants) à une table ; `table_id` vide le retire de sa table."""
    with transaction.atomic():
        try:
            guest = Guest.objects.select_for_update().get(pk=guest_id, event=event)
        except (Guest.DoesNotExist, ValueError, TypeError):
            raise SeatingError(_("Cet invité n'existe plus."))
        if guest.status != Guest.Status.CONFIRMED:
            raise SeatingError(_("%(name)s n'a pas confirmé sa présence : pas de place à table.") % {"name": guest.name})
        if not table_id:
            guest.table = None
            guest.save(update_fields=["table"])
            return guest, None
        table = _locked_table(event, table_id)
        free = table.capacity - _taken(table, excluding=guest.pk)
        if guest.party_size > free:
            raise SeatingError(ngettext(
                "%(label)s n'a plus assez de places : %(free)d libre, il en faut %(need)d pour %(name)s et ses accompagnants.",
                "%(label)s n'a plus assez de places : %(free)d libres, il en faut %(need)d pour %(name)s et ses accompagnants.",
                max(free, 0),
            ) % {"label": table.label, "free": max(free, 0), "need": guest.party_size, "name": guest.name})
        guest.table = table
        guest.save(update_fields=["table"])
        return guest, table


def _clean_capacity(value):
    try:
        capacity = int(value)
    except (TypeError, ValueError):
        raise SeatingError(_("Indiquez un nombre de places."))
    if not 1 <= capacity <= Table.MAX_CAPACITY:
        raise SeatingError(_("Une table a entre 1 et %(max)d places.") % {"max": Table.MAX_CAPACITY})
    return capacity


def _next_number(event):
    last = event.tables.order_by("-number").values_list("number", flat=True).first()
    return (last or 0) + 1


def add_table(event, name="", capacity=DEFAULT_CAPACITY):
    capacity = _clean_capacity(capacity)
    with transaction.atomic():
        # Verrou sur l'événement : deux ajouts en même temps ne reçoivent pas le même numéro
        Event.objects.select_for_update().get(pk=event.pk)
        if event.tables.count() >= MAX_TABLES:
            raise SeatingError(_("Un événement a au plus %(max)d tables.") % {"max": MAX_TABLES})
        return Table.objects.create(event=event, number=_next_number(event), name=(name or "").strip()[:60], capacity=capacity)


def add_tables(event, count, capacity):
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise SeatingError(_("Indiquez un nombre de tables."))
    if not 1 <= count <= MAX_TABLES:
        raise SeatingError(_("Choisissez entre 1 et %(max)d tables.") % {"max": MAX_TABLES})
    capacity = _clean_capacity(capacity)
    with transaction.atomic():
        Event.objects.select_for_update().get(pk=event.pk)
        if event.tables.count() + count > MAX_TABLES:
            raise SeatingError(_("Un événement a au plus %(max)d tables.") % {"max": MAX_TABLES})
        start = _next_number(event)
        return Table.objects.bulk_create(
            [Table(event=event, number=start + i, capacity=capacity) for i in range(count)]
        )


def update_table(event, table_id, name, capacity):
    capacity = _clean_capacity(capacity)
    with transaction.atomic():
        table = _locked_table(event, table_id)
        taken = _taken(table)
        if capacity < taken:
            raise SeatingError(ngettext(
                "%(label)s accueille déjà %(n)d personne : retirez des invités avant de réduire les places.",
                "%(label)s accueille déjà %(n)d personnes : retirez des invités avant de réduire les places.",
                taken,
            ) % {"label": table.label, "n": taken})
        table.name = (name or "").strip()[:60]
        table.capacity = capacity
        table.save(update_fields=["name", "capacity"])
        return table


def delete_table(event, table_id):
    """Supprime la table ; ses invités retournent dans « Sans table ». Les autres numéros ne changent pas."""
    with transaction.atomic():
        table = _locked_table(event, table_id)
        freed = table.guests.count()
        label = table.label
        table.delete()
    return label, freed


def auto_place(event):
    """Place les invités sans table dans les places libres, sans déplacer ceux qui sont déjà placés.

    Les plus grands groupes d'abord ; chaque groupe va à la table où il rentre le plus juste (les tables se
    remplissent donc complètement avant d'en ouvrir une autre) et un invité reste toujours avec ses accompagnants.
    Renvoie (nombre d'invités placés, invités qui n'ont pas trouvé de place).
    """
    with transaction.atomic():
        Event.objects.select_for_update().get(pk=event.pk)
        data = board(event)
        free = {v.table.pk: v.free for v in data["tables"]}
        order = {v.table.pk: v.table.number for v in data["tables"]}
        placed, left_out = [], []
        for guest in sorted(data["unseated"], key=lambda g: (-g.party_size, g.name.lower())):
            fits = [pk for pk, room in free.items() if room >= guest.party_size]
            if not fits:
                left_out.append(guest)
                continue
            pk = min(fits, key=lambda t: (free[t] - guest.party_size, order[t]))
            free[pk] -= guest.party_size
            guest.table_id = pk
            placed.append(guest)
        if placed:
            Guest.objects.bulk_update(placed, ["table"])
    return len(placed), left_out
