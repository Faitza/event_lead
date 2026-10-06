from datetime import date
from itertools import zip_longest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from ads.models import Ad
from events.listing import public_events_by_category
from events.models import Event, EventCategory

from .forms import ContactForm, HelpRequestForm, ReviewForm
from .content_cache import remember
from .help import HELP_PROFILES, HELP_UPDATED
from .search import search
from .middleware import set_language_cookie
from . import utm
from .models import Attribution, HelpRequest, Review
from .ratelimit import ratelimit

SERVICES = [
    ("bi-calendar2-heart", "svc-dashboard.jpg", gettext_lazy("Un tableau de bord pour tout piloter"), gettext_lazy("Mariage, gala, baptême ou conférence : créez l'événement, localisez le lieu sur une carte et gardez la main du début à la fin.")),
    ("bi-whatsapp", "svc-invitations.jpg", gettext_lazy("Invitations WhatsApp et e-mail"), gettext_lazy("Chaque invité reçoit un lien personnel, sans mot de passe, sur le canal qu'il utilise vraiment.")),
    ("bi-activity", "svc-presence.jpg", gettext_lazy("Qui vient, avec qui"), gettext_lazy("Présences, accompagnants et cadeaux se mettent à jour à chaque réponse : sachez exactement combien de chaises préparer.")),
    ("bi-gift", "svc-gifts.jpg", gettext_lazy("Cadeaux sans doublon"), gettext_lazy("Un cadeau choisi est aussitôt verrouillé pour les autres. La liste reste juste jusqu'au jour J.")),
    ("bi-ticket-perforated", "svc-tickets.jpg", gettext_lazy("Billetterie et paiements locaux"), gettext_lazy("Vendez vos billets et encaissez avec MonCash, NatCash, carte ou PayPal, avec les prix en gourdes et en dollars.")),
    ("bi-megaphone", "svc-partners.jpg", gettext_lazy("Une vitrine pour vos partenaires"), gettext_lazy("Traiteurs, fleuristes, photographes : leur publicité s'affiche après chaque réponse, et vous suivez les vues et les clics.")),
]


def build_parade(minimum=6):
    """Défilé de la page d'accueil : publications, événements publics et billets, en alternance."""
    ads = list(Ad.objects.live()[:6])
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


def _landing_content(slug):
    """Partie de l'accueil lue dans la base : gardée quelques minutes en mémoire (core/content_cache.py)."""
    public_events, categories, selected = public_events_by_category(slug)
    return {
        "reviews": list(Review.objects.filter(is_published=True)[:6]),
        "public_events": list(public_events[:6]),
        "categories": categories,
        "selected": selected,
        "parade": build_parade(),
        "all_categories": list(EventCategory.objects.all()),
    }


def landing(request):
    slug = request.GET.get("categorie", "")[:80]
    content = remember(f"landing:{slug}", lambda: _landing_content(slug))
    reviews, categories, selected = content["reviews"], content["categories"], content["selected"]
    context = {
        "public_events": content["public_events"],
        "categories": categories,
        "selected_category": selected,
        "parade": content["parade"],
        "usd_rate": settings.HTG_TO_USD_RATE,
        "services": SERVICES,
        # Tuiles « Pour chaque occasion » : toutes les catégories ; un clic ouvre les événements à venir de la catégorie
        # s'il y en a, sinon le formulaire de contact.
        "occasions": [(c, c in categories) for c in content["all_categories"]],
        "reviews": reviews,
        "review_form": ReviewForm(),
        "contact_form": ContactForm(),
    }
    return render(request, "core/landing.html", context)


@require_POST
@ratelimit("review", 5, 600)
def submit_review(request):
    form = ReviewForm(request.POST)
    if form.is_valid():
        if not form.cleaned_data["website"]:  # champ piège vide : vraie personne (sinon robot : rien n'est gardé)
            form.save()
        messages.success(request, _("Merci pour votre avis. Il sera publié après relecture par l'équipe."))
    else:
        messages.error(request, _("Votre avis n'a pas pu être enregistré. Vérifiez les champs."))
    return redirect(reverse("core:landing") + "#a-propos")


@require_POST
@ratelimit("contact", 5, 600)
def submit_contact(request):
    form = ContactForm(request.POST)
    if form.is_valid():
        if not form.cleaned_data["website"]:  # champ piège vide : vraie personne
            contact = form.save()
            utm.record(request, Attribution.Kind.CONTACT, contact.email)
        messages.success(request, _("Message envoyé. Notre équipe vous répondra rapidement."))
    else:
        messages.error(request, _("Le message n'a pas pu être envoyé. Vérifiez les champs."))
    return redirect(reverse("core:landing") + "#contact")


@ratelimit("help", 5, 600)
def help_page(request):
    """Questions fréquentes par profil, WhatsApp et formulaire « J'ai besoin d'aide »."""
    if request.method == "POST":
        form = HelpRequestForm(request.POST)
        if form.is_valid():
            if not form.cleaned_data["website"]:  # champ piège vide : vraie personne
                help_request = form.save()
                utm.record(request, Attribution.Kind.HELP, help_request.get_topic_display())
            return redirect(reverse("core:help") + "?envoye=1#demande")
    else:
        initial = {}
        if request.GET.get("sujet") in HelpRequest.Topic.values:
            initial["topic"] = request.GET["sujet"]
        if request.user.is_authenticated:
            initial["name"] = request.user.display_name
            initial["contact"] = request.user.email
        form = HelpRequestForm(initial=initial)
    if request.method == "POST":
        messages.error(request, _("La demande n'a pas pu être envoyée. Corrigez les champs en rouge."))
    return render(request, "core/help.html", {
        "profiles": HELP_PROFILES, "help_updated": HELP_UPDATED, "form": form, "sent": request.GET.get("envoye") == "1" and request.method == "GET",
    })


@ratelimit("search", 60, 60, methods=("GET",))
def search_page(request):
    """Recherche sur tout le site : événements publics, catégories, questions de l'aide, pages."""
    results = search(request.GET.get("q", ""))
    return render(request, "core/search.html", {"results": results, "q": results["query"]})


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


# Pages légales : un gabarit complet par langue (texte long, plus simple à relire et à faire valider qu'en .po).
LEGAL_UPDATED = date(2026, 10, 6)


def _legal(request, page):
    lang = (get_language() or "fr")[:2]
    if lang not in ("fr", "en", "ht"):
        lang = "fr"
    return render(request, f"core/legal/{page}_{lang}.html", {"legal_updated": LEGAL_UPDATED})


def privacy(request):
    """Politique de confidentialité (données personnelles)."""
    return _legal(request, "privacy")


def terms(request):
    """Conditions générales d'utilisation."""
    return _legal(request, "terms")
