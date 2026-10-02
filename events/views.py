"""Pages publiques d'événements et portail Organisateur VIP."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import vip_organizer_required
from ads.models import Ad

from .forms import EvaluationForm
from .listing import public_cards
from .models import Event, EventEvaluation, Guest


def explore(request):
    """Exploration des événements publics (fin du parcours invité)."""
    ads = Ad.objects.filter(is_active=True)[:3]
    return render(request, "events/explore.html", {"cards": public_cards(), "ads": ads})


def public_detail(request, pk):
    """Détail en lecture seule, sans informations sensibles (liste des invités, etc.)."""
    event = Event.objects.visible_to(request.user).filter(pk=pk).first()
    if event is None:
        raise Http404("Événement introuvable.")
    invitation = None
    if request.user.is_authenticated:
        invitation = event.guests.filter(user=request.user).first()
    siblings = []
    if event.group_id:
        siblings = event.group.events.public_active().upcoming().exclude(pk=event.pk)
    return render(request, "events/public_detail.html", {"event": event, "invitation": invitation, "siblings": siblings})


def _can_evaluate(event, user):
    if event.is_public:
        return False
    if not event.guests.filter(user=user, status=Guest.Status.CONFIRMED).exists():
        return False
    return timezone.localdate() >= event.evaluation_opens_on


@vip_organizer_required
def organizer_portal(request):
    user = request.user
    events = Event.objects.visible_to(user).order_by("date")
    today = timezone.localdate()
    upcoming, past = [], []
    evaluated = set(EventEvaluation.objects.filter(user=user).values_list("event_id", flat=True))
    for event in events:
        event.my_invitation = event.guests.filter(user=user).first()
        event.can_evaluate = _can_evaluate(event, user) and event.pk not in evaluated
        event.already_evaluated = event.pk in evaluated
        (past if event.date < today else upcoming).append(event)
    ads = Ad.objects.filter(is_active=True)
    return render(request, "events/organizer_portal.html", {"upcoming": upcoming, "past": past, "ads": ads})


@vip_organizer_required
def organizer_event_detail(request, pk):
    event = get_object_or_404(Event.objects.visible_to(request.user), pk=pk)
    invitation = event.guests.filter(user=request.user).first()
    return render(request, "events/organizer_event_detail.html", {
        "event": event, "invitation": invitation, "stats": event.stats(),
        "can_evaluate": _can_evaluate(event, request.user),
    })


@vip_organizer_required
def evaluate_event(request, pk):
    event = get_object_or_404(Event.objects.visible_to(request.user), pk=pk)
    if not _can_evaluate(event, request.user):
        messages.error(request, "L'évaluation de cet événement n'est pas encore ouverte.")
        return redirect("events:organizer_portal")
    instance = EventEvaluation.objects.filter(event=event, user=request.user).first()
    if instance:
        messages.info(request, "Vous avez déjà évalué cet événement. Merci.")
        return redirect("events:organizer_portal")
    form = EvaluationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        evaluation = form.save(commit=False)
        evaluation.event = event
        evaluation.user = request.user
        evaluation.save()
        messages.success(request, "Merci pour votre évaluation.")
        return redirect("events:organizer_portal")
    return render(request, "events/evaluate.html", {"event": event, "form": form})
