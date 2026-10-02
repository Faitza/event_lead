import csv

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import CustomUser
from ads.models import Ad
from events.models import Event, Guest
from gifts.models import Gift, GiftClaim
from payments.models import Payment

from .models import ContactMessage, HelpRequest, Review


@admin_required
def home(request):
    today = timezone.localdate()
    guests = Guest.objects.all()
    answered = guests.exclude(status=Guest.Status.PENDING).count()
    total_guests = guests.count()
    gift_units = Gift.objects.aggregate(s=Sum("quantity"))["s"] or 0
    ad_totals = Ad.objects.aggregate(views=Sum("views"), clicks=Sum("clicks"))
    revenue = Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(s=Sum("amount_htg"))["s"] or 0
    status_counts = dict(guests.values_list("status").annotate(n=Count("id")))
    context = {
        "stats": {
            "events": Event.objects.count(),
            "events_upcoming": Event.objects.filter(date__gte=today, status=Event.Status.ACTIVE).count(),
            "guests": total_guests,
            "confirmed": status_counts.get(Guest.Status.CONFIRMED, 0),
            "response_rate": round(answered * 100 / total_guests) if total_guests else 0,
            "gifts_taken": GiftClaim.objects.count(),
            "gift_units": gift_units,
            "ad_views": ad_totals["views"] or 0,
            "ad_clicks": ad_totals["clicks"] or 0,
            "revenue": revenue,
            "vip": CustomUser.objects.filter(is_vip=True).count(),
        },
        "status_breakdown": [
            (label, status_counts.get(value, 0), Guest(status=value).status_badge)
            for value, label in Guest.Status.choices
        ],
        "upcoming": Event.objects.filter(date__gte=today).annotate(num_guests=Count("guests")).order_by("date")[:5],
        "recent_replies": guests.exclude(replied_at=None).select_related("event").order_by("-replied_at")[:6],
        "recent_payments": Payment.objects.select_related("event", "user")[:5],
        "unread_messages": ContactMessage.objects.filter(is_read=False).count(),
        "new_help": HelpRequest.objects.filter(status=HelpRequest.Status.NEW).count(),
    }
    return render(request, "dashboard/home.html", context)


@admin_required
def inbox(request):
    return render(request, "dashboard/inbox.html", {
        "contact_messages": ContactMessage.objects.all()[:100],
        "reviews": Review.objects.all()[:100],
    })


@admin_required
@require_POST
def message_toggle_read(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.is_read = not msg.is_read
    msg.save(update_fields=["is_read"])
    return redirect("dashboard:inbox")


@admin_required
@require_POST
def review_toggle(request, pk):
    review = get_object_or_404(Review, pk=pk)
    review.is_published = not review.is_published
    review.save(update_fields=["is_published"])
    messages.success(request, "Avis publié." if review.is_published else "Avis masqué.")
    return redirect("dashboard:inbox")


# ---------------------------------------------------------------------------
# Demandes d'aide
# ---------------------------------------------------------------------------


def _csv_safe(value):
    """Neutralise les cellules qui seraient lues comme une formule par un tableur (texte saisi par le public)."""
    value = str(value)
    if value[:1] in ("=", "@", "\t", "\r"):
        return "'" + value
    if value[:1] in ("+", "-") and not set(value[1:]) <= set("0123456789 .-()"):
        return "'" + value
    return value


def _help_filter(request):
    status = request.GET.get("statut", "")
    return status if status in HelpRequest.Status.values else ""


@admin_required
def help_list(request):
    status = _help_filter(request)
    requests_qs = HelpRequest.objects.all()
    counts = dict(HelpRequest.objects.values_list("status").annotate(n=Count("id")))
    if status:
        requests_qs = requests_qs.filter(status=status)
    return render(request, "dashboard/help/list.html", {
        "help_requests": requests_qs[:200], "status": status, "statuses": HelpRequest.Status.choices,
        "tabs": [(value, label, counts.get(value, 0)) for value, label in HelpRequest.Status.choices],
        "total": sum(counts.values()),
    })


@admin_required
@require_POST
def help_set_status(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk)
    new_status = request.POST.get("status", "")
    if new_status in HelpRequest.Status.values:
        help_request.status = new_status
        help_request.save(update_fields=["status"])
        messages.success(request, f"Demande de {help_request.name} : {help_request.get_status_display().lower()}.")
    back = request.POST.get("filter", "")
    url = reverse("dashboard:help_list")
    return redirect(f"{url}?statut={back}" if back in HelpRequest.Status.values else url)


@admin_required
def help_export_csv(request):
    status = _help_filter(request)
    rows = HelpRequest.objects.all()
    if status:
        rows = rows.filter(status=status)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="demandes-aide-eventlead.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Reçue le", "Nom", "E-mail ou téléphone", "Sujet", "Message", "Statut"])
    for r in rows:
        writer.writerow([
            timezone.localtime(r.created_at).strftime("%d/%m/%Y %H:%M"), _csv_safe(r.name), _csv_safe(r.contact),
            r.get_topic_display(), _csv_safe(r.message), r.get_status_display(),
        ])
    return response
