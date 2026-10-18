"""Billets limités : on ne vend jamais plus de billets que de places (nombre maximum d'invités de l'événement).

Un billet en cours de paiement garde sa place quelques minutes ; s'il échoue, la place revient à la vente.
La vérification et l'enregistrement se font sous verrou sur l'événement : deux acheteurs du dernier billet,
au même instant, ne peuvent pas l'obtenir tous les deux.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from events.models import Event

from .models import Payment

PENDING_HOLD = timedelta(minutes=30)


class SoldOutError(Exception):
    def __init__(self, left):
        self.left = left
        super().__init__(f"{left} place(s) restante(s)")


def tickets_taken(event):
    holding = Q(status=Payment.Status.SUCCESS) | Q(
        status=Payment.Status.PENDING, created_at__gte=timezone.now() - PENDING_HOLD
    )
    taken = (
        Payment.objects.filter(holding, event=event, kind=Payment.Kind.TICKET)
        .aggregate(total=Sum("quantity"))["total"]
    )
    return taken or 0


def tickets_left(event):
    return max(event.max_guests - tickets_taken(event), 0)


def reserve(key, event, quantity, **fields):
    """Comme idempotency.reserve, mais refuse (SoldOutError) s'il ne reste pas assez de places."""
    try:
        with transaction.atomic():
            Event.objects.select_for_update().get(pk=event.pk)
            if key:
                previous = Payment.objects.filter(idempotency_key=key).first()
                if previous:  # même formulaire envoyé deux fois : on retrouve le premier paiement
                    return previous, False
            left = tickets_left(event)
            if quantity > left:
                raise SoldOutError(left)
            payment = Payment.objects.create(
                idempotency_key=key, status=Payment.Status.PENDING, kind=Payment.Kind.TICKET,
                event=event, quantity=quantity, **fields,
            )
            return payment, True
    except IntegrityError:
        if key is None:
            raise
        return Payment.objects.get(idempotency_key=key), False
