"""Tests des trois langues du site : français (par défaut), anglais et créole haïtien."""
import gettext
import importlib.util
import os
from datetime import date, time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from accounts.models import CustomUser
from events.messaging import invitation_links, invitation_url
from events.models import Event, EventCategory, Guest

PASSWORD = "MotDePasse-Solide-42"
ROOT = Path(settings.BASE_DIR)

# Mots de l'interface qui ne doivent plus apparaître en français dans les pages en anglais ou en créole.
FRENCH_UI_WORDS = ["Se connecter", "Mot de passe", "Tous droits réservés", "Enregistrer", "Retour"]


def load_tool():
    spec = importlib.util.spec_from_file_location("el_i18n", ROOT / "tools" / "i18n.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_event(**kw):
    defaults = dict(title="Mariage test", event_type="private", date=timezone.localdate() + timedelta(days=10),
                    time=time(15, 0), venue="Pétion-Ville", latitude=18.51, longitude=-72.28, max_guests=50,
                    allow_companions=True, max_companions=2)
    defaults.update(kw)
    return Event.objects.create(**defaults)


class LanguageSwitchTests(TestCase):
    def test_french_is_the_default_language(self):
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, '<html lang="fr"')

    def test_selector_offers_fr_en_kr_on_public_and_auth_pages(self):
        for url in (reverse("core:landing"), reverse("accounts:login"), reverse("core:help")):
            r = self.client.get(url)
            for code, short in (("fr", "FR"), ("en", "EN"), ("ht", "KR")):
                self.assertContains(r, f'value="{code}"', msg_prefix=url)
                self.assertContains(r, f">{short}</button>", msg_prefix=url)

    def test_choice_is_remembered_in_a_cookie_and_applied_to_next_pages(self):
        r = self.client.post(reverse("core:set_language"), {"language": "en", "next": reverse("core:help")})
        self.assertRedirects(r, reverse("core:help"), fetch_redirect_response=False)
        self.assertEqual(r.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        self.assertContains(self.client.get(reverse("core:landing")), '<html lang="en"')
        self.client.post(reverse("core:set_language"), {"language": "ht", "next": "/"})
        self.assertContains(self.client.get(reverse("core:help")), '<html lang="ht"')

    def test_unknown_language_is_ignored(self):
        r = self.client.post(reverse("core:set_language"), {"language": "xx", "next": "/"})
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, r.cookies)

    def test_next_must_stay_on_this_site(self):
        r = self.client.post(reverse("core:set_language"), {"language": "en", "next": "https://example.org/piege"})
        self.assertEqual(r["Location"], reverse("core:landing"))

    def test_language_change_needs_a_post(self):
        self.assertEqual(self.client.get(reverse("core:set_language")).status_code, 405)

    def test_logged_in_choice_is_saved_on_the_profile_and_follows_the_account(self):
        user = CustomUser.objects.create_user(username="a@x.ht", email="a@x.ht", password=PASSWORD)
        self.client.login(email="a@x.ht", password=PASSWORD)
        self.client.post(reverse("core:set_language"), {"language": "ht", "next": "/"})
        user.refresh_from_db()
        self.assertEqual(user.language, "ht")
        # Autre navigateur, sans cookie : la langue du profil s'applique
        other = self.client_class()
        other.login(email="a@x.ht", password=PASSWORD)
        self.assertContains(other.get(reverse("core:landing")), '<html lang="ht"')

    def test_lang_in_the_link_wins_and_is_remembered(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "fr"
        r = self.client.get(reverse("core:landing") + "?lang=en")
        self.assertContains(r, '<html lang="en"')
        self.assertEqual(r.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        self.assertContains(self.client.get(reverse("core:help")), '<html lang="en"')

    def test_switching_from_a_link_with_lang_really_switches(self):
        """Depuis un lien reçu en anglais (?lang=en), choisir KR ne doit pas revenir à l'anglais."""
        r = self.client.post(reverse("core:set_language"), {"language": "ht", "next": reverse("core:landing") + "?lang=en"})
        self.assertNotIn("lang=en", r["Location"])
        self.assertContains(self.client.get(r["Location"]), '<html lang="ht"')

    def test_browser_language_is_used_when_nothing_was_chosen(self):
        r = self.client.get(reverse("core:landing"), headers={"accept-language": "en-US,en;q=0.9"})
        self.assertContains(r, '<html lang="en"')

    def test_guest_can_use_the_invitation_in_any_language_without_account(self):
        guest = Guest.objects.create(event=make_event(), name="Carla", phone="+509 3712 3456")
        url = reverse("events:invitation", args=[guest.magic_token])
        for code in ("fr", "en", "ht"):
            r = self.client.get(f"{url}?lang={code}")
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, f'<html lang="{code}"')
            self.assertNotIn(reverse("accounts:login"), r.get("Location", ""))


class TranslatedTextTests(TestCase):
    def test_site_texts_follow_the_active_language(self):
        with translation.override("en"):
            self.assertEqual(_("Langue"), "Language")
        with translation.override("ht"):
            self.assertEqual(_("Langue"), "Lang")
        with translation.override("fr"):
            self.assertEqual(_("Langue"), "Langue")

    def test_dates_use_creole_month_and_day_names(self):
        from django.utils.dateformat import format as date_format

        day = date(2026, 10, 3)
        with translation.override("ht"):
            self.assertEqual(date_format(day, "j F Y"), "3 Oktòb 2026")
            self.assertEqual(date_format(day, "l"), "Samdi")
        with translation.override("en"):
            self.assertEqual(date_format(day, "j F Y"), "3 October 2026")
        with translation.override("fr"):
            self.assertEqual(date_format(day, "j F Y"), "3 octobre 2026")

    def test_form_validation_messages_are_translated(self):
        from django.core.exceptions import ValidationError
        from django.forms import CharField

        for code, expected in (("fr", "Ce champ est obligatoire."), ("en", "This field is required."),
                               ("ht", "Ou dwe ranpli chan sa a.")):
            with translation.override(code):
                with self.assertRaises(ValidationError) as ctx:
                    CharField().clean("")
                self.assertEqual(ctx.exception.messages, [expected])

    def test_default_category_names_are_translated_but_custom_ones_are_kept(self):
        wedding = EventCategory.objects.create(name="Mariage")
        custom = EventCategory.objects.create(name="Soirée de quartier")
        with translation.override("en"):
            self.assertEqual(wedding.label, "Wedding")
            self.assertEqual(custom.label, "Soirée de quartier")
        with translation.override("ht"):
            self.assertEqual(wedding.label, "Maryaj")
        with translation.override("fr"):
            self.assertEqual(wedding.label, "Mariage")


class PagesInEveryLanguageTests(TestCase):
    """Les pages principales s'affichent dans les trois langues, sans reste de texte français d'interface."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open(os.devnull, "w"))

    def pages(self, role):
        event = Event.objects.public_active().first()
        if role == "public":
            return [reverse("core:landing"), reverse("core:help"), reverse("events:explore"), reverse("payments:ticketing"),
                    reverse("accounts:login"), reverse("accounts:register"), reverse("ads:list"),
                    reverse("events:public_detail", args=[event.pk])]
        private = Event.objects.get(title__startswith="Mariage")
        guest = private.guests.first()
        return [
            reverse("dashboard:home"), reverse("dashboard:event_list"), reverse("dashboard:event_create"),
            reverse("dashboard:event_detail", args=[private.pk]), reverse("dashboard:event_edit", args=[private.pk]),
            reverse("dashboard:guest_list"), reverse("dashboard:guest_edit", args=[guest.pk]),
            reverse("dashboard:gift_list"), reverse("dashboard:ad_list"), reverse("dashboard:category_list"),
            reverse("dashboard:help_list"), reverse("dashboard:payment_history"), reverse("dashboard:inbox"),
        ]

    def check_pages(self, urls):
        for code in ("fr", "en", "ht"):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = code
            for url in urls:
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, f"{code} {url}")
                self.assertContains(r, f'<html lang="{code}"', msg_prefix=f"{code} {url}")
                if code != "fr":
                    html = r.content.decode()
                    for word in FRENCH_UI_WORDS:
                        self.assertNotIn(word, html, f"{code} {url} : « {word} » n'est pas traduit")

    def test_public_pages(self):
        self.check_pages(self.pages("public"))

    def test_dashboard_pages(self):
        self.client.login(email="admin@eventlead.ht", password="EventLead2026!")
        self.check_pages(self.pages("admin"))

    def test_invitation_steps(self):
        guest = Guest.objects.filter(status="pending").first() or Guest.objects.first()
        urls = [reverse(f"events:{name}", args=[guest.magic_token]) for name in ("invitation",)]
        self.check_pages(urls)


class InvitationMessageTests(TestCase):
    def setUp(self):
        self.event = make_event(title="Gala de la Fondation", date=timezone.localdate().replace(year=2030, month=3, day=5))
        self.request = RequestFactory().get("/", HTTP_HOST="testserver")

    def guest(self, language):
        return Guest.objects.create(event=self.event, name="Carla", phone="+509 3712 3456", email="c@x.ht", language=language)

    def test_french_message_is_the_original_one(self):
        links = invitation_links(self.request, self.guest("fr"))
        self.assertIn("Bonjour%20Carla%2C%20vous%20%C3%AAtes%20invit%C3%A9", links["whatsapp"])
        self.assertIn("05/03/2030", self.decoded(links["whatsapp"]))
        self.assertIn("Invitation%20%3A%20Gala", links["mailto"])

    def decoded(self, link):
        from urllib.parse import unquote

        return unquote(link)

    def test_english_message(self):
        links = invitation_links(self.request, self.guest("en"))
        text = self.decoded(links["whatsapp"])
        self.assertIn("Hello Carla, you are invited to “Gala de la Fondation” on March 5, 2030 at 15:00", text)
        self.assertIn("subject=Invitation: Gala", self.decoded(links["mailto"]))

    def test_creole_message(self):
        links = invitation_links(self.request, self.guest("ht"))
        text = self.decoded(links["whatsapp"])
        self.assertIn("Bonjou Carla, ou envite nan « Gala de la Fondation »", text)
        self.assertIn("05/03/2030", text)
        self.assertIn("subject=Envitasyon : Gala", self.decoded(links["mailto"]))

    def test_link_opens_the_page_in_the_guest_language(self):
        for code in ("fr", "en", "ht"):
            guest = self.guest(code)
            url = invitation_url(self.request, guest)
            self.assertTrue(url.endswith(f"?lang={code}"), url)
            self.assertIn(guest.magic_token.__str__(), url)

    def test_message_language_does_not_leak_into_the_admin_session(self):
        with translation.override("fr"):
            invitation_links(self.request, self.guest("ht"))
            self.assertEqual(translation.get_language(), "fr")

    def test_unknown_language_falls_back_to_french(self):
        guest = self.guest("fr")
        Guest.objects.filter(pk=guest.pk).update(language="xx")
        guest.refresh_from_db()
        self.assertIn("Bonjour", self.decoded(invitation_links(self.request, guest)["whatsapp"]))

    def test_admin_chooses_the_language_of_each_guest(self):
        admin = CustomUser.objects.create_user(username="ad@x.ht", email="ad@x.ht", password=PASSWORD, role="admin")
        self.client.login(email="ad@x.ht", password=PASSWORD)
        r = self.client.post(reverse("dashboard:guest_create"), {
            "event": self.event.pk, "name": "Marc", "email": "m@x.ht", "phone": "", "sent_via": "email", "language": "ht",
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        self.assertEqual(Guest.objects.get(name="Marc").language, "ht")
        self.assertIsNotNone(admin.pk)


class CatalogTests(TestCase):
    """Les catalogues .po/.mo versionnés doivent couvrir tous les textes du code (Windows n'a pas gettext)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool = load_tool()
        cls.extracted = cls.tool.extract()

    def test_every_text_has_an_english_and_creole_translation(self):
        for lang in ("en", "ht"):
            po = self.tool.read_po(ROOT / "locale" / lang / "LC_MESSAGES" / "django.po")
            missing = []
            for key, entry in self.extracted.items():
                found = po.get(key)
                if found is None or found.fuzzy or not all(found.msgstr):
                    missing.append(f"{entry.refs[0]} {entry.msgid[:60]!r}")
            self.assertEqual(missing, [], f"[{lang}] textes sans traduction ; lancez : python tools/i18n.py sync\n" + "\n".join(missing[:15]))

    def test_compiled_files_contain_the_translations(self):
        for lang in ("en", "ht"):
            catalog = gettext.GNUTranslations(open(ROOT / "locale" / lang / "LC_MESSAGES" / "django.mo", "rb"))
            for key, entry in self.extracted.items():
                ctx, msgid = key
                lookup = f"{ctx}\x04{msgid}" if ctx else msgid
                if entry.plural is not None:
                    self.assertIn((lookup, 0), catalog._catalog, f"[{lang}] {msgid!r} absent du .mo : python tools/i18n.py sync")
                else:
                    self.assertIn(lookup, catalog._catalog, f"[{lang}] {msgid!r} absent du .mo : python tools/i18n.py sync")

    def test_variables_are_kept_in_translations(self):
        self.assertEqual(self.tool.cmd_check(None), 0)
