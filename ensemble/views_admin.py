"""Tableau de bord : signalements de « Y aller ensemble » (/admin-dashboard/signalements/)."""
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from core.paging import paginate

from .models import Listing, MeetRequest, Profile, Report

TABS = ("a-traiter", "traites", "suspendus")


@admin_required
def report_list(request):
    tab = request.GET.get("onglet", "a-traiter")
    if tab not in TABS:
        tab = "a-traiter"
    reports = Report.objects.select_related("reporter__ensemble_profile", "reported__ensemble_profile", "event")
    counts = {
        "new": reports.filter(status=Report.Status.NEW).count(),
        "done": reports.exclude(status=Report.Status.NEW).count(),
        "suspended": reports.filter(status=Report.Status.SUSPENDED).count(),
    }
    if tab == "a-traiter":
        reports = reports.filter(status=Report.Status.NEW)
    elif tab == "traites":
        reports = reports.exclude(status=Report.Status.NEW)
    else:
        reports = reports.filter(status=Report.Status.SUSPENDED)
    totals = dict(Report.objects.values_list("reported").annotate(n=Count("id")))
    page_obj = paginate(request, reports, 20)
    for r in page_obj:
        r.total = totals.get(r.reported_id, 1)
    return render(request, "ensemble/dashboard/reports.html", {"tab": tab, "counts": counts, "page_obj": page_obj})


@admin_required
@require_POST
def report_action(request, pk):
    item = get_object_or_404(Report.objects.select_related("reported"), pk=pk)
    action = request.POST.get("action")
    person = item.reported
    now = timezone.now()
    if action == "warn":
        Profile.objects.filter(user=person).update(warned_at=now)
        status, text = Report.Status.WARNED, _("Avertissement envoyé : la personne le verra sur ses pages Y aller ensemble.")
    elif action == "remove":
        Profile.objects.filter(user=person).update(removed_at=now)
        Listing.objects.filter(user=person).delete()
        status, text = Report.Status.REMOVED, _("La personne est retirée de Y aller ensemble.")
    elif action == "suspend":
        if person.is_admin_role:
            messages.error(request, _("Un compte de l'équipe ne peut pas être suspendu ici."))
            return redirect("dashboard:ensemble_reports")
        person.is_active = False
        person.save(update_fields=["is_active"])
        Listing.objects.filter(user=person).delete()
        status, text = Report.Status.SUSPENDED, _("Compte suspendu : la personne ne peut plus se connecter.")
    elif action == "dismiss":
        status, text = Report.Status.DISMISSED, _("Signalement classé sans suite.")
    elif action == "reactivate":
        person.is_active = True
        person.save(update_fields=["is_active"])
        Profile.objects.filter(user=person).update(removed_at=None)
        Report.objects.filter(reported=person, status=Report.Status.SUSPENDED).update(status=Report.Status.DISMISSED)
        messages.success(request, _("Compte réactivé."))
        return redirect("dashboard:ensemble_reports")
    else:
        return redirect("dashboard:ensemble_reports")
    # Une décision vaut pour tous les signalements encore ouverts contre la même personne.
    Report.objects.filter(reported=person, status=Report.Status.NEW).update(status=status, handled_at=now, handled_by=request.user)
    item.refresh_from_db()
    if item.status != status:
        Report.objects.filter(pk=item.pk).update(status=status, handled_at=now, handled_by=request.user)
    messages.success(request, text)
    return redirect("dashboard:ensemble_reports")


@admin_required
def report_conversation(request, pk):
    """Conversation entre la personne qui signale et la personne signalée, pour décider en connaissance de cause."""
    item = get_object_or_404(Report.objects.select_related("reporter__ensemble_profile", "reported__ensemble_profile", "event"), pk=pk)
    pair = Q(sender=item.reporter, receiver=item.reported) | Q(sender=item.reported, receiver=item.reporter)
    threads = MeetRequest.objects.filter(pair).select_related("event").prefetch_related("messages")
    return render(request, "ensemble/dashboard/conversation.html", {"report": item, "threads": threads})
