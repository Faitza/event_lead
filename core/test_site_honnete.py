"""Liste « à éviter / à avoir » : avis validés, pages légales, favicon, pas de bouton pilule, pas de tiret long ni d'emoji."""
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import Review

BASE = Path(settings.BASE_DIR)


class ReviewModerationTests(TestCase):
    def test_review_sent_from_the_site_waits_for_the_team(self):
        r = self.client.post(reverse("core:submit_review"), {"name": "Nadège", "stars": 5, "text": "Très bien organisé."}, follow=True)
        self.assertContains(r, "Il sera publié après relecture")
        review = Review.objects.get()
        self.assertFalse(review.is_published)
        self.assertNotContains(self.client.get(reverse("core:landing")), "Très bien organisé.")

    def test_published_review_appears_on_the_home_page(self):
        Review.objects.create(name="Nadège", stars=5, text="Très bien organisé.", is_published=True)
        self.assertContains(self.client.get(reverse("core:landing")), "Très bien organisé.")

    def test_demo_data_publishes_no_review(self):
        call_command("seed_demo", "--reset", verbosity=0)
        self.assertTrue(Review.objects.exists())
        self.assertFalse(Review.objects.filter(is_published=True).exists())


class LegalPagesTests(TestCase):
    PAGES = {
        "core:privacy": {"fr": "Politique de confidentialité", "en": "Privacy policy", "ht": "Règ sou done pèsonèl"},
        "core:terms": {"fr": "Conditions d'utilisation", "en": "Terms of use", "ht": "Kondisyon itilizasyon"},
    }

    def test_each_page_exists_in_the_three_languages(self):
        for name, titles in self.PAGES.items():
            for lang, title in titles.items():
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
                r = self.client.get(reverse(name))
                self.assertEqual(r.status_code, 200, f"{name} {lang}")
                self.assertContains(r, f'<html lang="{lang}"')
                self.assertContains(r, title, html=False)
                self.assertContains(r, settings.CONTACT_EMAIL)

    def test_footer_links_to_both_pages(self):
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, f'href="{reverse("core:privacy")}"')
        self.assertContains(r, f'href="{reverse("core:terms")}"')

    def test_sign_up_form_mentions_both_pages(self):
        r = self.client.get(reverse("accounts:register"))
        self.assertContains(r, f'<a href="{reverse("core:terms")}">conditions d\'utilisation</a>', html=False)


class FaviconTests(TestCase):
    def test_pages_declare_the_icons(self):
        r = self.client.get(reverse("core:landing"))
        for f in ("favicon.ico", "img/favicon-32.png", "img/apple-touch-icon.png"):
            self.assertContains(r, f)
            self.assertTrue((BASE / "static" / f).exists(), f)

    def test_favicon_ico_url_redirects_to_the_file(self):
        r = self.client.get("/favicon.ico")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith("favicon.ico"))


class HonestDesignTests(TestCase):
    """Garde-fous sur le code : ce qui a été retiré ne doit pas revenir par mégarde."""

    def _files(self, *patterns):
        for pattern in patterns:
            yield from BASE.glob(pattern)

    def test_no_em_dash_in_visible_texts(self):
        for path in self._files("templates/**/*.html", "core/*.py", "events/*.py", "locale/*/LC_MESSAGES/django.po"):
            if path.name.startswith("test"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(chr(0x2014), text, path)
            self.assertNotIn("&mdash;", text, path)

    def test_no_emoji_in_templates(self):
        emoji = re.compile("[%s-%s%s-%s]" % (chr(0x1F300), chr(0x1FAFF), chr(0x2600), chr(0x27BF)))
        for path in self._files("templates/**/*.html", "static/js/*.js"):
            self.assertIsNone(emoji.search(path.read_text(encoding="utf-8")), path)

    def test_clickable_controls_are_not_pill_shaped(self):
        css = (BASE / "static/css/eventlead.css").read_text(encoding="utf-8")
        for selector in (".btn", ".user-pill", ".parade-toggle", ".cat-chip", ".fab-help", ".lang-group button", ".lang-toggle"):
            rule = re.search(r"^" + re.escape(selector) + r" \{[^}]*\}", css, re.M)
            self.assertIsNotNone(rule, selector)
            self.assertNotIn("999px", rule.group(0), selector)
