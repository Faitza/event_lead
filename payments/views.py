from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import admin_required
from events.models import Event

from .forms import PaymentForm
from .gateways import charge
from .models import Payment


def _usd(amount):
    return (Decimal(amount) * settings.HTG_TO_USD_RATE).quantize(Decimal("0.01"))


def ticketing(request):
    """Billetterie : événements payants avec prix en HTG et équivalent USD."""
    events = Event.objects.visible_to(request.user).filter(price_htg__isnull=False, price_htg__gt=0).upcoming()
    return render(request, "payments/ticketing.html", {"events": events, "rate": settings.HTG_TO_USD_RATE})


def _process(request, form, *, kind, amount, event=None, quantity=1):
    method = form.cleaned_data["method"]
    status, message = charge(method, form.cleaned_data, amount)
    guest = event.guests.filter(user=request.user).first() if event else None
    with transaction.atomic():
        payment = Payment.objects.create(
            kind=kind, event=event, guest=guest, user=request.user, method=method,
            amount_htg=amount, quantity=quantity, reference=Payment.generate_reference(method),
            status=status, payer_detail=form.cleaned_data.get("payer_detail", "")[:120],
        )
        if kind == Payment.Kind.ORGANIZER_ACCESS and status == Payment.Status.SUCCESS:
            user = request.user
            user.role = user.Role.ORGANIZER
            user.is_vip = True
            user.vip_since = timezone.now()
            user.save(update_fields=["role", "is_vip", "vip_since"])
    if status == Payment.Status.SUCCESS:
        return redirect("payments:success", reference=payment.reference)
    messages.error(request, f"{message} Référence : {payment.reference}.")
    return None


@login_required
def checkout(request, event_id):
    event = get_object_or_404(
        Event.objects.visible_to(request.user).filter(price_htg__gt=0), pk=event_id
    )
    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quantity = form.cleaned_data["quantity"]
        response = _process(request, form, kind=Payment.Kind.TICKET, amount=event.price_htg * quantity,
                            event=event, quantity=quantity)
        if response:
            return response
    return render(request, "payments/checkout.html", {
        "event": event, "form": form, "amount_htg": event.price_htg, "amount_usd": event.price_usd,
        "title": f"Billet - {event.title}", "allow_quantity": True,
    })


@login_required
def vip(request):
    """Page « Devenir Organisateur VIP » : accès bloqué tant que le paiement n'est pas confirmé."""
    user = request.user
    if user.is_admin_role:
        return redirect("dashboard:home")
    if user.is_vip_organizer:
        return redirect("events:organizer_portal")
    amount = settings.VIP_ORGANIZER_PRICE_HTG
    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        response = _process(request, form, kind=Payment.Kind.ORGANIZER_ACCESS, amount=amount)
        if response:
            messages.success(request, "Bienvenue parmi les Organisateurs VIP.")
            return response
    return render(request, "payments/vip.html", {
        "form": form, "amount_htg": amount, "amount_usd": _usd(amount), "title": "Accès Organisateur VIP",
        "allow_quantity": False,
    })


@login_required
def success(request, reference):
    payment = get_object_or_404(Payment.objects.select_related("event"), reference=reference)
    if payment.user_id != request.user.pk and not request.user.is_admin_role:
        raise PermissionDenied
    return render(request, "payments/success.html", {"payment": payment})


@admin_required
def history(request):
    payments = Payment.objects.select_related("event", "user", "guest")
    status = request.GET.get("status", "")
    method = request.GET.get("method", "")
    kind = request.GET.get("kind", "")
    q = request.GET.get("q", "").strip()
    if status in dict(Payment.Status.choices):
        payments = payments.filter(status=status)
    if method in dict(Payment.Method.choices):
        payments = payments.filter(method=method)
    if kind in dict(Payment.Kind.choices):
        payments = payments.filter(kind=kind)
    if q:
        payments = payments.filter(Q(reference__icontains=q) | Q(user__email__icontains=q) | Q(event__title__icontains=q))
    total = payments.filter(status=Payment.Status.SUCCESS).aggregate(s=Sum("amount_htg"))["s"] or Decimal("0")
    return render(request, "dashboard/payments/history.html", {
        "payments": payments, "status": status, "method": method, "kind": kind, "q": q,
        "statuses": Payment.Status.choices, "methods": Payment.Method.choices, "kinds": Payment.Kind.choices,
        "total_htg": total, "total_usd": _usd(total),
    })
