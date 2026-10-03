"""Pointage de l'entrée le jour J (tableau de bord administrateur)."""
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import admin_required

from . import checkin
from .models import CheckIn, Event, Guest

RECENT = 25


@admin_required
def checkin_index(request):
    """Choix de l'événement à pointer : ceux d'aujourd'hui et à venir d'abord."""
    today = timezone.localdate()
    events = list(
        Event.objects.annotate(
            confirmed=Count("guests", filter=Q(guests__status=Guest.Status.CONFIRMED), distinct=True),
            arrived=Count("guests", filter=Q(guests__checked_in_at__isnull=False), distinct=True),
        ).filter(guests__isnull=False).distinct()
    )
    upcoming = sorted((e for e in events if e.date >= today), key=lambda e: (e.date, e.time))
    past = sorted((e for e in events if e.date < today), key=lambda e: (e.date, e.time), reverse=True)
    return render(request, "dashboard/checkin/index.html", {"upcoming": upcoming, "past": past, "today": today})


def _page_context(event):
    recent = event.check_ins.select_related("guest")[:RECENT]
    return {
        "event": event,
        "stats": checkin.stats(event),
        "recent": recent,
        "refused_count": event.check_ins.filter(result__in=CheckIn.REFUSED).count(),
        "on_site_count": event.check_ins.filter(result=CheckIn.Result.WALK_IN).count(),
        "now": timezone.now(),
    }


@admin_required
def checkin_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    context = _page_context(event)
    context["is_today"] = event.date == timezone.localdate()
    return render(request, "dashboard/checkin/event.html", context)


@admin_required
@require_GET
def checkin_live(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return HttpResponse(render_to_string("dashboard/checkin/_live.html", _page_context(event), request=request))


def _outcome_response(outcome):
    return JsonResponse(checkin.describe(outcome))


@admin_required
@require_POST
def checkin_scan(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return _outcome_response(checkin.scan(event, request.POST.get("code", ""), request.user))


@admin_required
@require_POST
def checkin_manual(request, pk):
    event = get_object_or_404(Event, pk=pk)
    guest = get_object_or_404(Guest, pk=request.POST.get("guest", 0) or 0, event=event)
    return _outcome_response(checkin.check_in_guest(event, guest, request.user, CheckIn.Source.MANUAL))


@admin_required
@require_GET
def checkin_search(request, pk):
    event = get_object_or_404(Event, pk=pk)
    results = [
        {
            "id": g.pk, "name": g.name, "code": g.entry_code, "party": g.party_size,
            "status": g.get_status_display(), "tone": g.status_badge,
            "arrived": g.checked_in_at is not None,
            "arrived_at": checkin.clock(g.checked_in_at) if g.checked_in_at else "",
        }
        for g in checkin.search_guests(event, request.GET.get("q", ""))
    ]
    return JsonResponse({"results": results})


@admin_required
@require_POST
def checkin_walk_in(request, pk):
    event = get_object_or_404(Event, pk=pk)
    name = request.POST.get("name", "").strip()[:150]
    if not name:
        return JsonResponse({"error": _("Indiquez le nom de la personne.")}, status=400)
    try:
        companions = min(max(int(request.POST.get("companions", "0") or 0), 0), 20)
    except ValueError:
        companions = 0
    outcome = checkin.add_walk_in(event, name, companions, request.POST.get("phone", "").strip()[:30], request.user)
    return _outcome_response(outcome)


@admin_required
@require_POST
def checkin_cancel(request, pk, guest_pk):
    event = get_object_or_404(Event, pk=pk)
    guest = get_object_or_404(Guest, pk=guest_pk, event=event)
    cancelled = checkin.cancel_check_in(event, guest, request.user)
    return JsonResponse({"cancelled": cancelled is not None, "name": guest.name})
