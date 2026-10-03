from itertools import zip_longest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from ads.models import Ad
from events.listing import public_events_by_category
from events.models import Event

from .forms import ContactForm, HelpRequestForm, ReviewForm
from .help import HELP_PROFILES
from .middleware import set_language_cookie
from .models import HelpRequest, Review

SERVICES = [
    ("bi-calendar2-heart", gettext_lazy("Un tableau de bord pour tout piloter"), gettext_lazy("Mariage, gala, baptême ou conférence : créez l'événement, localisez le lieu sur une carte et gardez la main du début à la fin.")),
    ("bi-whatsapp", gettext_lazy("Invitations WhatsApp et e-mail"), gettext_lazy("Chaque invité reçoit un lien personnel, sans mot de passe, sur le canal qu'il utilise vraiment.")),
    ("bi-activity", gettext_lazy("Qui vient, avec qui"), gettext_lazy("Présences, accompagnants et cadeaux se mettent à jour à chaque réponse : sachez exactement combien de chaises préparer.")),
    ("bi-gift", gettext_lazy("Cadeaux sans doublon"), gettext_lazy("Un cadeau choisi est aussitôt verrouillé pour les autres. La liste reste juste jusqu'au jour J.")),
    ("bi-ticket-perforated", gettext_lazy("Billetterie et paiements locaux"), gettext_lazy("Vendez vos billets et encaissez avec MonCash, NatCash, carte ou PayPal, avec les prix en gourdes et en dollars.")),
    ("bi-megaphone", gettext_lazy("Une vitrine pour vos partenaires"), gettext_lazy("Traiteurs, fleuristes, photographes : leur publicité s'affiche après chaque réponse, et vous suivez les vues et les clics.")),
]


def build_parade(minimum=6):
    """Défilé de la page d'accueil : publications, événements publics et billets, en alternance."""
    ads = list(Ad.objects.filter(is_active=True)[:6])
    events = list(Event.objects.public_active().upcoming().select_related("category")[:6])
    tickets = [e for e in events if e.is_paid]
    rows = zip_longest(
        [("ad", a) for a in ads],
        [("event", e) for e in events],
        [("ticket", t) for t in tickets],
    )
    items = [item for row in rows for item in row if item]
    if items and len(items) < minimum:
        items = (items * (minimum // len(items) + 1))[:max(minimum, len(items))]
    return items


def landing(request):
    reviews = Review.objects.filter(is_published=True)[:6]
    public_events, categories, selected = public_events_by_category(request.GET.get("categorie", ""))
    context = {
        "public_events": public_events[:6],
        "categories": categories,
        "selected_category": selected,
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
        messages.success(request, _("Merci pour votre avis."))
    else:
        messages.error(request, _("Votre avis n'a pas pu être enregistré. Vérifiez les champs."))
    return redirect(reverse("core:landing") + "#a-propos")


@require_POST
def submit_contact(request):
    form = ContactForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, _("Message envoyé. Notre équipe vous répondra rapidement."))
    else:
        messages.error(request, _("Le message n'a pas pu être envoyé. Vérifiez les champs."))
    return redirect(reverse("core:landing") + "#contact")


def help_page(request):
    """Questions fréquentes par profil, WhatsApp et formulaire « J'ai besoin d'aide »."""
    if request.method == "POST":
        form = HelpRequestForm(request.POST)
        if form.is_valid():
            if not form.cleaned_data["website"]:  # champ piège vide : vraie personne
                form.save()
            return redirect(reverse("core:help") + "?envoye=1#demande")
    else:
        initial = {}
        if request.GET.get("sujet") in HelpRequest.Topic.values:
            initial["topic"] = request.GET["sujet"]
        if request.user.is_authenticated:
            initial["name"] = request.user.display_name
            initial["contact"] = request.user.email
        form = HelpRequestForm(initial=initial)
    return render(request, "core/help.html", {
        "profiles": HELP_PROFILES, "form": form, "sent": request.GET.get("envoye") == "1" and request.method == "GET",
    })


@require_POST
def set_language(request):
    """Sélecteur FR | EN | KR : mémorise la langue dans un cookie, et sur le profil si la personne est connectée."""
    code = request.POST.get("language", "")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = reverse("core:landing")
    # Un lien reçu avec ?lang=xx ne doit pas annuler le choix qui vient d'être fait
    parts = urlsplit(target)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "lang"])
    response = redirect(urlunsplit(parts._replace(query=query)))
    if code in dict(settings.LANGUAGES):
        set_language_cookie(response, code)
        if request.user.is_authenticated and request.user.language != code:
            request.user.language = code
            request.user.save(update_fields=["language"])
    return response
