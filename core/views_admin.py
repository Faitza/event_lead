from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import CustomUser
from ads.models import Ad
from events.models import Event, Guest
from gifts.models import Gift, GiftClaim
from payments.models import Payment

from .models import ContactMessage, Review


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
