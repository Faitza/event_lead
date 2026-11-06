"""Petits détails du site (docs/details.md) : recherche, provenance des liens utm_*, mode sombre, bandeau cookies,
retour en haut, lien « Aller au contenu », impression, copier, confirmations, date de mise à jour, messages d'erreur."""
from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from core.models import Attribution, HelpRequest
from core.search import fold, search
from events.models import Event, EventCategory, Guest
from payments.models import Payment

BASE = Path(settings.BASE_DIR)
PASSWORD = "Mot-de-passe-solide-2026"
UTM = "?utm_source=facebook&utm_medium=publication&utm_campaign=mariages-octobre"


def make_event(**kw):
    defaults = dict(title="Gala des étoiles", event_type="public", date=timezone.localdate() + timedelta(days=10),
                    time=time(19, 0), venue="Hôtel Montana, Pétion-Ville", max_guests=100)
    defaults.update(kw)
    return Event.objects.create(**defaults)


class SearchTests(TestCase):
    def setUp(self):
        self.cat = EventCategory.objects.create(name="Mariage", slug="mariage", icon_name="bi-heart")
        self.public = make_event(title="Mariage au jardin", category=self.cat)
        self.private = make_event(title="Mariage privé de Sarah", event_type="private")
        self.past = make_event(title="Mariage passé", date=timezone.localdate() - timedelta(days=3))

    def test_fold_ignores_accents_and_case(self):
        self.assertEqual(fold("Événement Baptême"), "evenement bapteme")

    def test_finds_public_upcoming_events_only(self):
        results = search("mariage")
        self.assertEqual(results["events"], [self.public])
        self.assertEqual(results["categories"], [self.cat])

    def test_accents_do_not_matter(self):
        self.assertEqual(search("petion")["events"], [self.public])
        self.assertEqual(search("HÔTEL montana")["events"], [self.public])

    def test_finds_help_questions_and_pages(self):
        results = search("moncash")
        self.assertIn("paiement-moncash", [q["slug"] for q in results["questions"]])
        self.assertIn(reverse("payments:ticketing"), [p["url"] for p in results["pages"]])

    def test_page_shows_results_with_links(self):
        r = self.client.get(reverse("core:search"), {"q": "moncash"})
        self.assertContains(r, reverse("core:help") + "#faq-paiement-moncash")
        self.assertContains(r, "résultats pour « moncash »")

    def test_empty_and_unknown_queries(self):
        self.assertEqual(self.client.get(reverse("core:search")).status_code, 200)
        r = self.client.get(reverse("core:search"), {"q": "zzzqqq"})
        self.assertContains(r, "Aucun résultat")
        self.assertContains(r, reverse("core:help") + "#demande")

    def test_private_event_never_appears(self):
        r = self.client.get(reverse("core:search"), {"q": "Sarah"})
        self.assertNotContains(r, "Mariage privé de Sarah")

    def test_search_is_in_the_menu(self):
        self.assertContains(self.client.get(reverse("core:landing")), f'href="{reverse("core:search")}"')

    def test_page_exists_in_three_languages(self):
        for lang, word in (("en", "Search"), ("ht", "Chèche")):
            r = self.client.get(reverse("core:search") + f"?lang={lang}")
            self.assertContains(r, word)


class UtmTests(TestCase):
    def test_utm_on_arrival_is_kept_and_attached_to_a_help_request(self):
        self.client.get(reverse("core:landing") + UTM)
        self.client.post(reverse("core:help"), {"name": "Lise", "contact": "lise@x.ht", "topic": "other", "message": "Bonjour"})
        a = Attribution.objects.get()
        self.assertEqual((a.kind, a.source, a.medium, a.campaign), ("help", "facebook", "publication", "mariages-octobre"))
        self.assertEqual(a.landing_page, "/")

    def test_no_utm_no_record(self):
        self.client.get(reverse("core:landing"))
        self.client.post(reverse("core:submit_contact"), {"name": "Lise", "email": "lise@x.ht", "message": "Bonjour"})
        self.assertFalse(Attribution.objects.exists())

    def test_contact_and_signup_are_recorded(self):
        self.client.get(reverse("events:explore") + UTM)
        self.client.post(reverse("core:submit_contact"), {"name": "Lise", "email": "lise@x.ht", "message": "Bonjour"})
        self.client.post(reverse("accounts:register"), {
            "first_name": "Lise", "last_name": "Pierre", "email": "lise@x.ht", "phone": "",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertEqual(sorted(Attribution.objects.values_list("kind", flat=True)), ["contact", "signup"])
        signup = Attribution.objects.get(kind="signup")
        self.assertEqual(signup.user.email, "lise@x.ht")
        self.assertEqual(signup.landing_page, reverse("events:explore"))

    def test_successful_payment_is_recorded(self):
        user = CustomUser.objects.create_user(username="o@x.ht", email="o@x.ht", password=PASSWORD, role="organizer")
        self.client.force_login(user)
        self.client.get(reverse("core:landing") + UTM)
        self.client.post(reverse("payments:vip"), {"method": "moncash", "phone": "3712 3456", "otp": "123456",
                                                   "idem": "0123456789abcdef0123456789abcdef"})
        payment = Payment.objects.get()
        a = Attribution.objects.get(kind="payment")
        self.assertIn(payment.reference, a.label)
        self.assertEqual(a.user, user)

    def test_values_are_trimmed(self):
        self.client.get(reverse("core:landing") + "?utm_source=" + "x" * 500)
        self.client.post(reverse("core:help"), {"name": "Lise", "contact": "lise@x.ht", "topic": "other", "message": "Bonjour"})
        self.assertEqual(len(Attribution.objects.get().source), 120)

    def test_dashboard_report_and_link_builder(self):
        admin = CustomUser.objects.create_user(username="a@x.ht", email="a@x.ht", password=PASSWORD, role="admin")
        Attribution.objects.create(kind="help", source="facebook", campaign="oct", label="Autre question")
        Attribution.objects.create(kind="signup", source="facebook", campaign="oct", label="l@x.ht")
        self.client.force_login(admin)
        url = reverse("dashboard:utm_report")
        r = self.client.get(url)
        self.assertContains(r, "Provenance des visites")
        self.assertEqual(r.context["summary"][0]["total"], 2)
        r = self.client.get(url, {"page": "/evenements/", "source": "whatsapp", "medium": "statut", "campaign": "gala"})
        self.assertEqual(r.context["built_link"],
                         "http://testserver/evenements/?utm_source=whatsapp&utm_medium=statut&utm_campaign=gala")
        self.assertContains(r, 'data-copy="http://testserver/evenements/?utm_source=whatsapp')

    def test_report_is_for_the_team_only(self):
        self.assertEqual(self.client.get(reverse("dashboard:utm_report")).status_code, 302)


class PageDetailsTests(TestCase):
    def setUp(self):
        self.home = self.client.get(reverse("core:landing")).content.decode()

    def test_skip_link_and_content_target(self):
        self.assertIn('class="skip-link" href="#contenu"', self.home)
        self.assertIn('id="contenu"', self.home)
        self.assertIn("Aller au contenu", self.home)

    def test_dark_mode_button_back_to_top_progress_and_cookie_note(self):
        for marker in ("data-theme-toggle", "data-to-top", 'id="el-progress"', "data-cookie-note", "js/details.js",
                       "css/details.css", 'localStorage.getItem("el-theme")'):
            self.assertIn(marker, self.home)

    def test_dark_mode_is_never_the_default(self):
        # La page s'affiche toujours en clair ; seul le bouton (gardé dans le navigateur) active le mode sombre
        self.assertNotIn('data-theme="dark"', self.home)
        self.assertNotIn("prefers-color-scheme", (BASE / "static/css/details.css").read_text(encoding="utf-8"))

    def test_cookie_note_matches_the_privacy_page(self):
        self.assertIn("seulement les cookies nécessaires", self.home)
        self.assertIn(reverse("core:privacy"), self.home)
        privacy = self.client.get(reverse("core:privacy")).content.decode()
        self.assertIn("utm_", privacy)

    def test_help_page_has_update_date_print_and_collapsible_faq(self):
        r = self.client.get(reverse("core:help"))
        self.assertContains(r, "Dernière mise à jour")
        self.assertContains(r, "data-print")
        self.assertContains(r, '<details class="faq-item"')

    def test_help_form_failure_shows_a_message(self):
        r = self.client.post(reverse("core:help"), {"name": "", "contact": "", "topic": "other", "message": ""})
        self.assertContains(r, "La demande n&#x27;a pas pu être envoyée")
        self.assertFalse(HelpRequest.objects.exists())

    def test_public_event_has_copy_and_print(self):
        event = make_event()
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, f'data-copy="{event.venue}"')
        self.assertContains(r, "data-print")

    def test_ticket_has_copy_code_and_print(self):
        event = make_event(event_type="private")
        guest = Guest.objects.create(event=event, name="Carla", status="confirmed", replied_at=timezone.now())
        r = self.client.get(reverse("events:invitation_ticket", args=[guest.magic_token]))
        self.assertContains(r, f'data-copy="{guest.entry_code}"')
        self.assertContains(r, "data-print")

    def test_legal_pages_can_be_printed(self):
        self.assertContains(self.client.get(reverse("core:terms")), "data-print")

    def test_print_stylesheet_hides_navigation(self):
        css = (BASE / "static/css/details.css").read_text(encoding="utf-8")
        self.assertIn("@media print", css)
        self.assertIn(".el-nav", css.split("@media print")[1])

    def test_important_actions_ask_for_confirmation(self):
        thanks = (BASE / "templates/dashboard/thanks/event.html").read_text(encoding="utf-8")
        self.assertIn('data-confirm="{{ t_send }}"', thanks)
        self.assertIn("data-confirm=", (BASE / "templates/dashboard/ads/list.html").read_text(encoding="utf-8"))
        js = (BASE / "static/js/details.js").read_text(encoding="utf-8")
        self.assertIn("data-confirm", js)
        self.assertIn("input[type=password]", js)

    def test_dashboard_has_dark_mode_button_and_provenance_link(self):
        admin = CustomUser.objects.create_user(username="a@x.ht", email="a@x.ht", password=PASSWORD, role="admin")
        self.client.force_login(admin)
        r = self.client.get(reverse("dashboard:home"))
        self.assertContains(r, "data-theme-toggle")
        self.assertContains(r, reverse("dashboard:utm_report"))
