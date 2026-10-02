from itertools import zip_longest

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ads.models import Ad
from events.listing import group_events, public_cards
from events.models import Event

from .forms import ContactForm, ReviewForm
from .models import Review

SERVICES = [
    ("bi-calendar2-heart", "Un tableau de bord pour tout piloter", "Mariage, gala, baptême ou conférence : créez l'événement, localisez le lieu sur une carte et gardez la main du début à la fin."),
    ("bi-whatsapp", "Invitations WhatsApp et e-mail", "Chaque invité reçoit un lien personnel, sans mot de passe, sur le canal qu'il utilise vraiment."),
    ("bi-activity", "Qui vient, avec qui", "Présences, accompagnants et cadeaux se mettent à jour à chaque réponse : sachez exactement combien de chaises préparer."),
    ("bi-gift", "Cadeaux sans doublon", "Un cadeau choisi est aussitôt verrouillé pour les autres. La liste reste juste jusqu'au jour J."),
    ("bi-ticket-perforated", "Billetterie et paiements locaux", "Vendez vos billets et encaissez avec MonCash, NatCash, carte ou PayPal, avec les prix en gourdes et en dollars."),
    ("bi-megaphone", "Une vitrine pour vos partenaires", "Traiteurs, fleuristes, photographes : leur publicité s'affiche après chaque réponse, et vous suivez les vues et les clics."),
]


def build_parade(minimum=6):
    """Défilé de la page d'accueil : publications, événements publics (un groupe = une carte) et billets."""
    ads = list(Ad.objects.filter(is_active=True)[:6])
    events = list(Event.objects.public_active().upcoming().select_related("group"))
    cards = group_events(events)[:6]
    tickets = [e for e in events if e.is_paid][:6]
    rows = zip_longest(
        [("ad", a) for a in ads],
        [(c["kind"], c["event"] if c["kind"] == "event" else c) for c in cards],
        [("ticket", t) for t in tickets],
    )
    items = [item for row in rows for item in row if item]
    if items and len(items) < minimum:
        items = (items * (minimum // len(items) + 1))[:max(minimum, len(items))]
    return items


def landing(request):
    reviews = Review.objects.filter(is_published=True)[:6]
    context = {
        "public_cards": public_cards(limit=6),
        "parade": build_parade(),
        "usd_rate": settings.HTG_TO_USD_RATE,
        "services": SERVICES,
        "reviews": reviews,
        "review_form": ReviewForm(),
        "contact_form": ContactForm(),
    }
    return render(request, "core/landing.html", context)


@require_POST
def submit_review(request):
    form = ReviewForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "Merci pour votre avis.")
    else:
        messages.error(request, "Votre avis n'a pas pu être enregistré. Vérifiez les champs.")
    return redirect(reverse("core:landing") + "#a-propos")


@require_POST
def submit_contact(request):
    form = ContactForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "Message envoyé. Notre équipe vous répondra rapidement.")
    else:
        messages.error(request, "Le message n'a pas pu être envoyé. Vérifiez les champs.")
    return redirect(reverse("core:landing") + "#contact")
