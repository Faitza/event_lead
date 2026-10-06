"""Recherche sur tout le site (/recherche/?q=...) : événements publics, catégories, questions de l'aide, pages.

Les questions et les pages sont cherchées dans la langue affichée, sans tenir compte des accents ni des majuscules.
"""
import unicodedata

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from events.models import Event, EventCategory

from .help import HELP_PROFILES

MAX_QUERY = 80

# Pages du site : (titre, description, nom d'URL, ancre, mots-clés en plus)
PAGES = [
    (_("Accueil"), _("Présentation d'EventLead, événements à venir et contact."), "core:landing", "", "eventlead accueil home"),
    (_("Services"), _("Invitations WhatsApp et e-mail, suivi des présences, cadeaux, billetterie, partenaires."), "core:landing", "#services", "service invitation whatsapp cadeau"),
    (_("Événements publics"), _("Tous les événements publics à venir, par catégorie."), "events:explore", "", "evenement agenda calendrier"),
    (_("Billetterie"), _("Acheter un billet avec MonCash, NatCash, carte ou PayPal."), "payments:ticketing", "", "billet ticket moncash natcash paypal carte payer"),
    (_("Aide"), _("Questions fréquentes, WhatsApp et formulaire « J'ai besoin d'aide »."), "core:help", "", "aide faq question support"),
    (_("Contact"), _("Écrire à l'équipe EventLead."), "core:landing", "#contact", "contact message ecrire telephone email"),
    (_("À propos"), _("Qui nous sommes et les avis de nos clients."), "core:landing", "#a-propos", "propos avis equipe"),
    (_("Devenir Organisateur VIP"), _("Ouvrir un compte Organisateur et activer l'accès VIP."), "accounts:register_organizer", "", "vip organisateur compte inscription"),
    (_("Connexion"), _("Se connecter à son espace."), "accounts:login", "", "connexion login compte mot de passe"),
    (_("Politique de confidentialité"), _("Les données que nous gardons et pourquoi, les cookies."), "core:privacy", "", "confidentialite donnees cookies vie privee"),
    (_("Conditions d'utilisation"), _("Les règles d'utilisation du site."), "core:terms", "", "conditions regles cgu"),
]


def fold(text):
    """Minuscules, sans accents : « Événement » et « evenement » se trouvent l'un l'autre."""
    text = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _matches(query_words, *texts):
    haystack = fold(" ".join(str(t) for t in texts))
    return all(w in haystack for w in query_words)


def search(query):
    query = " ".join(str(query).split())[:MAX_QUERY]
    words = [w for w in fold(query).split() if w]
    if not words:
        return {"query": query, "events": [], "categories": [], "questions": [], "pages": [], "total": 0}

    events_q = Q()
    for word in query.split():
        events_q &= (Q(title__icontains=word) | Q(venue__icontains=word) | Q(description__icontains=word)
                     | Q(category__name__icontains=word))
    events = list(Event.objects.public_active().upcoming().filter(events_q)
                  .select_related("category").order_by("date", "time")[:12])
    # SQLite ne compare pas les lettres accentuées sans tenir compte de la casse : second passage en Python
    if len(events) < 12:
        seen = {e.pk for e in events}
        for e in (Event.objects.public_active().upcoming().exclude(pk__in=seen)
                  .select_related("category").order_by("date", "time")[:300]):
            if _matches(words, e.title, e.venue, e.description, e.category.name if e.category else ""):
                events.append(e)
                if len(events) >= 12:
                    break

    categories = [c for c in EventCategory.objects.all() if _matches(words, c.name)]
    questions = [
        {"slug": slug, "question": question, "answer": answer, "profile": profile["title"]}
        for profile in HELP_PROFILES for slug, question, answer in profile["questions"]
        if _matches(words, question, answer)
    ][:15]
    pages = [
        {"title": title, "text": text, "url": reverse(name) + anchor}
        for title, text, name, anchor, keywords in PAGES
        if _matches(words, title, text, keywords)
    ]
    total = len(events) + len(categories) + len(questions) + len(pages)
    return {"query": query, "events": events, "categories": categories, "questions": questions, "pages": pages,
            "total": total}
