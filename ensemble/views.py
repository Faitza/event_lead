"""Pages « Y aller ensemble » côté membres (/ensemble/)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.models import CustomUser
from core.ratelimit import ratelimit
from events.models import Event
from payments.models import Payment

from .forms import LISTING_FILTERS, MessageForm, ProfileForm, ReportForm, RequestForm
from .models import Block, Listing, MeetRequest, Message, Profile, Report


# --- Règles communes -------------------------------------------------------------------------------------------

def open_event(pk):
    """Événement public, actif et pas encore passé : seul cas où l'on peut s'afficher et faire des demandes."""
    event = Event.objects.public_active().filter(pk=pk).first()
    if event is None or event.is_past:
        raise Http404(_("Événement introuvable."))
    return event


def profile_of(user):
    return Profile.objects.filter(user=user).first()


def visible_listings(event, user):
    """Les autres personnes affichées pour l'événement, sans les personnes bloquées ni retirées par l'équipe."""
    return (Listing.objects.filter(event=event, user__is_active=True, user__ensemble_profile__removed_at__isnull=True)
            .exclude(user=user).exclude(user_id__in=Block.hidden_ids(user))
            .select_related("user__ensemble_profile"))


def event_block_context(event, user):
    """Données du bloc « Y aller ensemble » de la page d'un événement (None quand le bloc ne s'affiche pas)."""
    if not event.is_public or event.status != Event.Status.ACTIVE or event.is_past:
        return None
    others = Listing.objects.filter(event=event, user__is_active=True, user__ensemble_profile__removed_at__isnull=True)
    mine = None
    if user.is_authenticated:
        mine = Listing.objects.filter(event=event, user=user).first()
        others = others.exclude(user=user).exclude(user_id__in=Block.hidden_ids(user))
    others = others.select_related("user__ensemble_profile")
    return {"count": others.count(), "preview": [l.user.ensemble_profile for l in others[:4]], "mine": mine,
            "ticket_needed": needs_ticket(event) and not (user.is_authenticated and can_ask(user, event))}


def needs_ticket(event):
    return bool(event.price_htg and event.price_htg > 0)


def can_ask(user, event):
    """Proposer d'y aller ensemble demande un billet payé quand l'entrée est payante (décision du 20 octobre 2026).
    Un paiement en attente ou échoué ne compte pas. Entrée gratuite : pas de billet à acheter, donc pas de condition."""
    if not needs_ticket(event):
        return True
    return Payment.objects.filter(user=user, event=event, kind=Payment.Kind.TICKET, status=Payment.Status.SUCCESS).exists()


def _blocked_by_team(request, profile):
    if profile and profile.is_removed:
        messages.error(request, _("L'équipe EventLead vous a retiré de Y aller ensemble. Écrivez-nous depuis la page Aide si vous pensez que c'est une erreur."))
        return True
    return False


def pending_count(user):
    return MeetRequest.objects.filter(receiver=user, status=MeetRequest.Status.PENDING, event__date__gte=timezone.localdate()).exclude(sender_id__in=Block.hidden_ids(user)).count()


# --- S'afficher pour un événement ------------------------------------------------------------------------------

@login_required
def join(request, pk):
    event = open_event(pk)
    profile = profile_of(request.user)
    if _blocked_by_team(request, profile):
        return redirect(event.get_absolute_url())
    listing = Listing.objects.filter(event=event, user=request.user).first()
    initial = None if profile else {"first_name": request.user.first_name}
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile, listing=listing, initial=initial)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["website"]:  # champ piège rempli : robot, rien n'est gardé
            return redirect(event.get_absolute_url())
        now = timezone.now()
        item = form.save(commit=False)
        item.user = request.user
        if not item.pk:
            item.adult_confirmed_at = now
            item.rules_accepted_at = now
        item.save()
        Listing.objects.update_or_create(event=event, user=request.user, defaults=form.listing_values())
        messages.success(request, _("Vous êtes affiché pour cet événement. Vous pouvez maintenant voir les autres personnes."))
        return redirect("ensemble:people", pk=event.pk)
    return render(request, "ensemble/profile_form.html", {"event": event, "form": form, "profile": profile, "listing": listing})


@login_required
@require_POST
def leave(request, pk):
    event = get_object_or_404(Event, pk=pk)
    Listing.objects.filter(event=event, user=request.user).delete()
    # Les demandes encore en attente pour cet événement tombent avec.
    MeetRequest.objects.filter(event=event, status=MeetRequest.Status.PENDING).filter(Q(sender=request.user) | Q(receiver=request.user)).delete()
    messages.success(request, _("Vous n'êtes plus affiché pour cet événement."))
    return redirect(event.get_absolute_url())


# --- Qui va à l'événement --------------------------------------------------------------------------------------

@login_required
def people(request, pk):
    event = open_event(pk)
    profile = profile_of(request.user)
    if _blocked_by_team(request, profile):
        return redirect(event.get_absolute_url())
    mine = Listing.objects.filter(event=event, user=request.user).first()
    if mine is None:
        # On ne voit les autres qu'après s'être soi-même affiché.
        return redirect("ensemble:join", pk=event.pk)
    listings = visible_listings(event, request.user)
    counts = {"all": listings.count()}
    for key, field in LISTING_FILTERS.items():
        counts[key] = listings.filter(**{field: True}).count()
    counts["ville"] = listings.filter(user__ensemble_profile__city__iexact=profile.city).count()
    active = request.GET.get("filtre", "")
    if active in LISTING_FILTERS:
        listings = listings.filter(**{LISTING_FILTERS[active]: True})
    elif active == "ville":
        listings = listings.filter(user__ensemble_profile__city__iexact=profile.city)
    else:
        active = ""
    requests = MeetRequest.objects.filter(event=event).filter(Q(sender=request.user) | Q(receiver=request.user))
    state = {r.other(request.user).pk: r for r in requests}
    listings = list(listings)
    for item in listings:
        item.req = state.get(item.user_id)
    return render(request, "ensemble/people.html", {
        "event": event, "listings": listings, "counts": counts, "active": active,
        "profile": profile, "pending": pending_count(request.user), "request_form": RequestForm(), "report_form": ReportForm(),
        "can_ask": can_ask(request.user, event),
    })


@login_required
@require_POST
@ratelimit("ensemble-demande", 20, 3600)
def send_request(request, pk, user_id):
    event = open_event(pk)
    profile = profile_of(request.user)
    if _blocked_by_team(request, profile):
        return redirect(event.get_absolute_url())
    target = get_object_or_404(CustomUser, pk=user_id, is_active=True)
    back = redirect("ensemble:people", pk=event.pk)
    if not can_ask(request.user, event):
        messages.error(request, _("Achetez d'abord votre billet pour cet événement : ensuite vous pourrez proposer à quelqu'un d'y aller avec vous."))
        return back
    if target == request.user or not Listing.objects.filter(event=event, user=request.user).exists():
        return back
    if not visible_listings(event, request.user).filter(user=target).exists():
        messages.error(request, _("Cette personne n'est plus affichée pour cet événement."))
        return back
    form = RequestForm(request.POST)
    if not form.is_valid() or form.cleaned_data["website"]:
        messages.error(request, _("Votre petit mot est trop long (300 caractères au plus)."))
        return back
    reverse_request = MeetRequest.objects.filter(sender=target, receiver=request.user, event=event).first()
    if reverse_request:
        messages.info(request, _("Cette personne vous a déjà fait une demande. Répondez-lui dans Mes demandes."))
        return redirect("ensemble:requests")
    try:
        with transaction.atomic():
            MeetRequest.objects.create(sender=request.user, receiver=target, event=event, note=form.cleaned_data["note"].strip())
    except IntegrityError:
        pass  # déjà envoyée (double clic)
    messages.success(request, _("Demande envoyée. Vous pourrez vous écrire si la personne accepte."))
    return back


# --- Mes demandes ----------------------------------------------------------------------------------------------

@login_required
def requests_list(request):
    user = request.user
    hidden = Block.hidden_ids(user)
    today = timezone.localdate()
    base = MeetRequest.objects.select_related("event", "sender__ensemble_profile", "receiver__ensemble_profile")
    received = base.filter(receiver=user, status=MeetRequest.Status.PENDING, event__date__gte=today).exclude(sender_id__in=hidden)
    # Une demande refusée reste « envoyée » pour la personne qui l'a faite : elle n'est pas prévenue du refus.
    sent = base.filter(sender=user, status__in=[MeetRequest.Status.PENDING, MeetRequest.Status.DECLINED], event__date__gte=today).exclude(receiver_id__in=hidden)
    accepted = base.filter(Q(sender=user) | Q(receiver=user), status=MeetRequest.Status.ACCEPTED).exclude(sender_id__in=hidden).exclude(receiver_id__in=hidden)
    tab = request.GET.get("onglet", "recues")
    items = {"recues": received, "envoyees": sent, "acceptees": accepted}.get(tab)
    if items is None:
        tab, items = "recues", received
    return render(request, "ensemble/requests.html", {
        "tab": tab, "items": items, "counts": {"recues": received.count(), "envoyees": sent.count(), "acceptees": accepted.count()},
        "profile": profile_of(user), "report_form": ReportForm(),
    })


@login_required
@require_POST
def answer_request(request, pk):
    item = get_object_or_404(MeetRequest, pk=pk, receiver=request.user, status=MeetRequest.Status.PENDING)
    if _blocked_by_team(request, profile_of(request.user)) or Block.between(item.sender, item.receiver):
        return redirect("ensemble:requests")
    item.responded_at = timezone.now()
    if request.POST.get("action") == "accept":
        item.status = MeetRequest.Status.ACCEPTED
        item.save(update_fields=["status", "responded_at"])
        messages.success(request, _("Demande acceptée. Vous pouvez maintenant vous écrire."))
        return redirect("ensemble:conversation", pk=item.pk)
    item.status = MeetRequest.Status.DECLINED
    item.save(update_fields=["status", "responded_at"])
    messages.success(request, _("Demande refusée."))
    return redirect("ensemble:requests")


# --- Messages --------------------------------------------------------------------------------------------------

def _conversations(user):
    hidden = Block.hidden_ids(user)
    return (MeetRequest.objects.filter(Q(sender=user) | Q(receiver=user), status=MeetRequest.Status.ACCEPTED)
            .exclude(sender_id__in=hidden).exclude(receiver_id__in=hidden)
            .select_related("event", "sender__ensemble_profile", "receiver__ensemble_profile")
            .order_by("-last_message_at", "-responded_at"))


@login_required
def inbox(request):
    conversations = list(_conversations(request.user))
    if conversations:
        return redirect("ensemble:conversation", pk=conversations[0].pk)
    return render(request, "ensemble/conversation.html", {"conversations": [], "profile": profile_of(request.user)})


@login_required
@ratelimit("ensemble-message", 60, 600)
def conversation(request, pk):
    user = request.user
    item = get_object_or_404(_conversations(user), pk=pk)
    other = item.other(user)
    profile = profile_of(user)
    form = MessageForm(request.POST or None)
    if request.method == "POST":
        if _blocked_by_team(request, profile):
            return redirect("ensemble:conversation", pk=item.pk)
        if not item.chat_is_open:
            messages.error(request, _("Cette conversation est fermée."))
        elif form.is_valid():
            now = timezone.now()
            Message.objects.create(request=item, sender=user, body=form.cleaned_data["body"].strip())
            MeetRequest.objects.filter(pk=item.pk).update(last_message_at=now)
            return redirect(reverse("ensemble:conversation", args=[item.pk]) + "#fin")
    return render(request, "ensemble/conversation.html", {
        "conversations": _conversations(user), "item": item, "other": other, "other_profile": getattr(other, "ensemble_profile", None),
        "chat": item.messages.all(), "form": form, "profile": profile, "report_form": ReportForm(),
        "i_accepted": item.receiver_id == user.pk,
    })


# --- Bloquer, signaler -----------------------------------------------------------------------------------------

def _safe_next(request, fallback):
    target = request.POST.get("next", "")
    return target if target.startswith("/ensemble/") else fallback


@login_required
@require_POST
def block(request, user_id):
    target = get_object_or_404(CustomUser, pk=user_id)
    if target != request.user:
        Block.objects.get_or_create(blocker=request.user, blocked=target)
        messages.success(request, _("Personne bloquée. Elle ne peut plus vous voir ni vous écrire."))
    return redirect(_safe_next(request, reverse("ensemble:requests")))


@login_required
@require_POST
@ratelimit("ensemble-signalement", 10, 3600)
def report(request, user_id):
    target = get_object_or_404(CustomUser, pk=user_id)
    form = ReportForm(request.POST)
    if target != request.user and form.is_valid():
        event = Event.objects.filter(pk=request.POST.get("event") or 0).first()
        Report.objects.create(reporter=request.user, reported=target, event=event,
                              reason=form.cleaned_data["reason"], details=form.cleaned_data["details"].strip())
        if form.cleaned_data["also_block"]:
            Block.objects.get_or_create(blocker=request.user, blocked=target)
        messages.success(request, _("Merci. L'équipe EventLead va lire votre signalement."))
    return redirect(_safe_next(request, reverse("ensemble:requests")))
