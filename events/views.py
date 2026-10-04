"""Pages publiques d'événements et portail Organisateur VIP."""
from django.contrib import messages
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.decorators import vip_organizer_required
from core.paging import paginate
from ads.models import Ad

from .forms import EvaluationForm
from .listing import public_events_by_category
from .models import Event, EventEvaluation, Guest


def explore(request):
    """Exploration des événements publics (fin du parcours invité)."""
    events, categories, selected = public_events_by_category(request.GET.get("categorie", ""))
    ads = Ad.objects.filter(is_active=True)[:3]
    page = paginate(request, events, 12)
    return render(request, "events/explore.html", {
        "events": page.object_list, "page_obj": page, "categories": categories, "selected_category": selected, "ads": ads,
    })


def public_detail(request, pk):
    """Détail en lecture seule, sans informations sensibles (liste des invités, etc.)."""
    event = Event.objects.visible_to(request.user).select_related("category").filter(pk=pk).first()
    if event is None:
        raise Http404(_("Événement introuvable."))
    invitation = None
    if request.user.is_authenticated:
        invitation = event.guests.filter(user=request.user).first()
    return render(request, "events/public_detail.html", {"event": event, "invitation": invitation})


def _can_evaluate(event, user, invitation=False):
    """`invitation` : l'invitation de la personne si elle est déjà chargée (None si elle n'en a pas)."""
    if event.is_public:
        return False
    if invitation is not False:
        if invitation is None or invitation.status != Guest.Status.CONFIRMED:
            return False
    elif not event.guests.filter(user=user, status=Guest.Status.CONFIRMED).exists():
        return False
    return timezone.localdate() >= event.evaluation_opens_on


@vip_organizer_required
def organizer_portal(request):
    user = request.user
    # Invitation de la personne chargée en une seule requête pour tous les événements (pas une par événement)
    events = Event.objects.visible_to(user).select_related("category").order_by("date").prefetch_related(
        Prefetch("guests", queryset=Guest.objects.filter(user=user), to_attr="my_invitations")
    )
    today = timezone.localdate()
    upcoming, past = [], []
    evaluated = set(EventEvaluation.objects.filter(user=user).values_list("event_id", flat=True))
    for event in events:
        event.my_invitation = event.my_invitations[0] if event.my_invitations else None
        event.can_evaluate = _can_evaluate(event, user, event.my_invitation) and event.pk not in evaluated
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
        messages.error(request, _("L'évaluation de cet événement n'est pas encore ouverte."))
        return redirect("events:organizer_portal")
    instance = EventEvaluation.objects.filter(event=event, user=request.user).first()
    if instance:
        messages.info(request, _("Vous avez déjà évalué cet événement. Merci."))
        return redirect("events:organizer_portal")
    form = EvaluationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        evaluation = form.save(commit=False)
        evaluation.event = event
        evaluation.user = request.user
        evaluation.save()
        messages.success(request, _("Merci pour votre évaluation."))
        return redirect("events:organizer_portal")
    return render(request, "events/evaluate.html", {"event": event, "form": form})
