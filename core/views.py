from django.contrib import messages
from django.db.models import Avg
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from events.models import Event, Guest

from .forms import ContactForm, ReviewForm
from .models import Review

SERVICES = [
    ("bi-calendar2-heart", "Gestion d'événements", "Créez et pilotez mariages, galas et conférences depuis un tableau de bord unique."),
    ("bi-whatsapp", "Invitations WhatsApp et e-mail", "Chaque invité reçoit un lien personnel, sans mot de passe, sur le canal qu'il préfère."),
    ("bi-geo-alt", "Cartographie", "Le lieu est localisé automatiquement et affiché sur une carte interactive."),
    ("bi-activity", "Suivi en temps réel", "Présences, accompagnants et cadeaux se mettent à jour au fil des réponses."),
    ("bi-megaphone", "Publicités partenaires", "Mettez en avant vos sponsors après chaque réponse et suivez vues et clics."),
    ("bi-gift", "Liste de cadeaux", "Une liste sans doublon : un cadeau choisi est aussitôt verrouillé pour les autres."),
]


def landing(request):
    reviews = Review.objects.filter(is_published=True)[:6]
    avg = Review.objects.filter(is_published=True).aggregate(a=Avg("stars"))["a"]
    public_events = Event.objects.public_active().upcoming()[:4]
    context = {
        "public_events": public_events,
        "services": SERVICES,
        "reviews": reviews,
        "stats": {
            "events": Event.objects.exclude(status=Event.Status.DRAFT).count(),
            "invitations": Guest.objects.count(),
            "satisfaction": round(avg * 20) if avg else 98,
        },
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
