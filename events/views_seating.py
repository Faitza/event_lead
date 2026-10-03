"""Plan de table (tableau de bord administrateur)."""
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import admin_required

from . import seating
from .models import Event, Guest


@admin_required
def seating_index(request):
    """Choix de l'événement : ceux qui ont des invités présents, à venir d'abord."""
    today = timezone.localdate()
    cards = []
    events = Event.objects.annotate(
        confirmed=Count("guests", filter=Q(guests__status=Guest.Status.CONFIRMED), distinct=True),
    ).filter(confirmed__gt=0)
    for event in events:
        data = seating.board(event)
        cards.append({"event": event, "stats": data["stats"]})
    upcoming = sorted((c for c in cards if c["event"].date >= today), key=lambda c: (c["event"].date, c["event"].time))
    past = sorted((c for c in cards if c["event"].date < today), key=lambda c: (c["event"].date, c["event"].time), reverse=True)
    return render(request, "dashboard/seating/index.html", {"upcoming": upcoming, "past": past})


def _board_context(event):
    data = seating.board(event)
    data["event"] = event
    return data


def _board_html(request, event):
    return render_to_string("dashboard/seating/_board.html", _board_context(event), request=request)


@admin_required
def seating_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    context = _board_context(event)
    context.update({"default_tables": seating.DEFAULT_TABLES, "default_capacity": seating.DEFAULT_CAPACITY,
                    "max_capacity": seating.Table.MAX_CAPACITY, "max_tables": seating.MAX_TABLES})
    return render(request, "dashboard/seating/event.html", context)


@admin_required
@require_GET
def seating_live(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return JsonResponse({"ok": True, "html": _board_html(request, event)})


@admin_required
def seating_print(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return render(request, "dashboard/seating/print.html", _board_context(event))


def _answer(request, event, action, message=""):
    """Exécute `action` ; renvoie le plan à jour, ou l'erreur écrite pour l'administrateur."""
    try:
        extra = action()
    except seating.SeatingError as error:
        return JsonResponse({"ok": False, "error": str(error), "html": _board_html(request, event)}, status=400)
    return JsonResponse({"ok": True, "message": extra or message, "html": _board_html(request, event)})


@admin_required
@require_POST
def seating_seat(request, pk):
    """Glisser un invité sur une table (ou le remettre dans « Sans table » avec table vide)."""
    event = get_object_or_404(Event, pk=pk)

    def action():
        guest, table = seating.seat_guest(event, request.POST.get("guest"), request.POST.get("table"))
        if table is None:
            return _("%(name)s est retiré(e) de sa table.") % {"name": guest.name}
        return _("%(name)s est placé(e) à la %(label)s.") % {"name": guest.name, "label": table.label}

    return _answer(request, event, action)


@admin_required
@require_POST
def seating_table_add(request, pk):
    event = get_object_or_404(Event, pk=pk)

    def action():
        table = seating.add_table(event, request.POST.get("name", ""), request.POST.get("capacity", seating.DEFAULT_CAPACITY))
        return _("%(label)s ajoutée.") % {"label": table.label}

    return _answer(request, event, action)


@admin_required
@require_POST
def seating_table_bulk(request, pk):
    """Création de plusieurs tables d'un coup (12 tables de 12 places par défaut)."""
    event = get_object_or_404(Event, pk=pk)

    def action():
        created = seating.add_tables(event, request.POST.get("count"), request.POST.get("capacity"))
        return ngettext("%(n)d table créée.", "%(n)d tables créées.", len(created)) % {"n": len(created)}

    return _answer(request, event, action)


@admin_required
@require_POST
def seating_table_update(request, pk, table_pk):
    event = get_object_or_404(Event, pk=pk)

    def action():
        table = seating.update_table(event, table_pk, request.POST.get("name", ""), request.POST.get("capacity"))
        return _("%(label)s enregistrée.") % {"label": table.label}

    return _answer(request, event, action)


@admin_required
@require_POST
def seating_table_delete(request, pk, table_pk):
    event = get_object_or_404(Event, pk=pk)

    def action():
        label, freed = seating.delete_table(event, table_pk)
        if freed:
            return ngettext(
                "%(label)s supprimée : %(n)d invité retourne dans « Sans table ».",
                "%(label)s supprimée : %(n)d invités retournent dans « Sans table ».", freed,
            ) % {"label": label, "n": freed}
        return _("%(label)s supprimée.") % {"label": label}

    return _answer(request, event, action)


@admin_required
@require_POST
def seating_auto(request, pk):
    event = get_object_or_404(Event, pk=pk)

    def action():
        placed, left_out = seating.auto_place(event)
        parts = [ngettext("%(n)d invité placé.", "%(n)d invités placés.", placed) % {"n": placed}] if placed else []
        if left_out:
            parts.append(ngettext(
                "%(n)d invité n'a pas trouvé de place : ajoutez une table.",
                "%(n)d invités n'ont pas trouvé de place : ajoutez une table.", len(left_out),
            ) % {"n": len(left_out)})
        return " ".join(parts) or _("Personne à placer pour le moment.")

    return _answer(request, event, action)
