"""Liste « 20 choses à vérifier avant de lancer ton site » (docs/lancement.md) : HTTPS, titres, partage sur les réseaux,
sitemap et robots.txt, liens cassés, anti-spam, compteur de visites privé, page 404."""
import os
import re
import subprocess
import sys
from datetime import time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from core.models import ContactMessage, PageView, Review
from events.models import Event, EventCategory

BASE = Path(settings.BASE_DIR)
PASSWORD = "Mot-de-passe-solide-2026"
BROWSER = {"HTTP_USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0"}
PUBLIC_PAGES = ["/", "/evenements/", "/billetterie/", "/aide/", "/confidentialite/", "/conditions-utilisation/",
                "/recherche/?q=mariage", "/connexion/", "/inscription/"]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.images, self.title = [], [], ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "img":
            self.images.append(attrs)
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def make_event(**kw):
    defaults = dict(title="Gala des étoiles", event_type="public", date=timezone.localdate() + timedelta(days=10),
                    time=time(19, 0), venue="Hôtel Montana, Pétion-Ville", max_guests=100,
                    description="Une soirée de gala au profit des écoles.")
    defaults.update(kw)
    return Event.objects.create(**defaults)


class HttpsTests(TestCase):
    def _prod_settings(self):
        env = dict(os.environ, DEBUG="False", SECRET_KEY="x" * 60, ALLOWED_HOSTS="eventlead.ht")
        code = ("from django.conf import settings as s;"
                "print(s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE)")
        out = subprocess.run([sys.executable, "manage.py", "shell", "-c", code], cwd=BASE, env=env,
                             capture_output=True, text=True, timeout=120)
        return out.stdout.strip().splitlines()[-1]

    def test_production_forces_https(self):
        self.assertEqual(self._prod_settings(), "True 31536000 True True")

    def test_local_computer_is_not_forced(self):
        # Sur le PC (DEBUG=True), pas de redirection vers https://
        self.assertEqual(self.client.get("/").status_code, 200)


class SeoTests(TestCase):
    def test_home_has_title_description_and_share_image(self):
        html = self.client.get("/").content.decode()
        self.assertIn('<meta name="description"', html)
        self.assertIn('<meta property="og:image" content="http://testserver/static/img/partage.jpg', html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', html)
        self.assertIn('<link rel="canonical" href="http://testserver/">', html)
        self.assertNotIn('name="robots"', html)
        self.assertTrue((BASE / "static/img/partage.jpg").exists())

    def test_share_image_has_the_right_size(self):
        from PIL import Image

        self.assertEqual(Image.open(BASE / "static/img/partage.jpg").size, (1200, 630))

    def test_event_page_shares_its_own_title_and_photo(self):
        event = make_event()
        html = self.client.get(event.get_absolute_url()).content.decode()
        self.assertIn('<meta property="og:title" content="Gala des étoiles">', html)
        self.assertIn("Une soirée de gala", html.split('property="og:description"')[1][:200])
        self.assertRegex(html, r'<meta property="og:image" content="http://testserver/(static|media)/')

    def test_private_pages_are_hidden_from_google(self):
        for url in ("/connexion/", "/inscription/", "/recherche/?q=x"):
            self.assertContains(self.client.get(url), '<meta name="robots" content="noindex, nofollow">', msg_prefix=url)

    def test_every_public_page_has_its_own_title(self):
        make_event()
        titles = set()
        for url in PUBLIC_PAGES:
            parser = LinkParser()
            parser.feed(self.client.get(url).content.decode())
            title = " ".join(parser.title.split())
            self.assertNotEqual(title, "EventLead | EventLead", url)
            titles.add(title)
        self.assertEqual(len(titles), len(PUBLIC_PAGES))

    def test_robots_txt(self):
        r = self.client.get("/robots.txt")
        self.assertEqual(r["Content-Type"], "text/plain; charset=utf-8")
        body = r.content.decode()
        for line in ("Disallow: /admin-dashboard/", "Disallow: /invitation/", "Disallow: /mon-espace/",
                     "Sitemap: http://testserver/sitemap.xml"):
            self.assertIn(line, body)

    def test_sitemap_lists_public_pages_and_public_events_only(self):
        public = make_event()
        private = make_event(title="Mariage privé", event_type="private")
        past = make_event(title="Passé", date=timezone.localdate() - timedelta(days=2))
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<loc>http://testserver/</loc>", body)
        self.assertIn("<loc>http://testserver/billetterie/</loc>", body)
        self.assertIn(f"<loc>http://testserver{public.get_absolute_url()}</loc>", body)
        self.assertNotIn(private.get_absolute_url() + "<", body)
        self.assertNotIn(past.get_absolute_url() + "<", body)
        for loc in re.findall(r"<loc>http://testserver(.*?)</loc>", body):
            self.assertEqual(self.client.get(loc).status_code, 200, loc)


class BrokenLinksTests(TestCase):
    """Suit chaque lien interne des pages publiques (connecté ou non) : aucun ne doit mener à une erreur."""

    def setUp(self):
        call_command("seed_demo", verbosity=0)

    def _crawl(self):
        seen, broken = set(), []
        for start in PUBLIC_PAGES:
            parser = LinkParser()
            parser.feed(self.client.get(start).content.decode())
            for img in parser.images:
                self.assertIn("alt", img, f"{start} : image sans texte alternatif {img.get('src')}")
            for href in parser.links:
                url, _ = urldefrag(href)
                parts = urlsplit(url)
                if not url or parts.scheme in ("mailto", "tel", "https", "http") or parts.netloc or url in seen:
                    continue
                seen.add(url)
                status = self.client.get(url).status_code
                if status >= 400:
                    broken.append(f"{start} -> {url} ({status})")
        return seen, broken

    def test_no_broken_link_for_visitors(self):
        seen, broken = self._crawl()
        self.assertGreater(len(seen), 15)
        self.assertEqual(broken, [])

    def test_no_broken_link_for_a_signed_in_guest(self):
        user = CustomUser.objects.create_user(username="g@x.ht", email="g@x.ht", password=PASSWORD)
        self.client.force_login(user)
        self.assertEqual(self._crawl()[1], [])

    def test_unknown_page_shows_the_custom_404(self):
        r = self.client.get("/cette-page-n-existe-pas/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "EventLead", status_code=404)
        self.assertContains(r, 'href="/"', status_code=404)


class AntiSpamTests(TestCase):
    def test_contact_trap_filled_by_a_robot_saves_nothing(self):
        data = {"name": "Bot", "email": "bot@x.ht", "message": "Promo", "website": "http://spam.example"}
        r = self.client.post(reverse("core:submit_contact"), data)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ContactMessage.objects.exists())
        data["website"] = ""
        self.client.post(reverse("core:submit_contact"), data)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_review_trap(self):
        self.client.post(reverse("core:submit_review"), {"name": "Bot", "stars": 5, "text": "Super", "website": "x"})
        self.assertFalse(Review.objects.exists())

    def test_register_trap(self):
        self.client.post(reverse("accounts:register"), {
            "first_name": "Bot", "last_name": "B", "email": "bot@x.ht", "password1": PASSWORD, "password2": PASSWORD,
            "website": "http://spam.example",
        })
        self.assertFalse(CustomUser.objects.filter(email="bot@x.ht").exists())

    def test_traps_are_in_the_pages_and_hidden(self):
        for url in ("/", "/inscription/", "/aide/"):
            self.assertContains(self.client.get(url), 'class="hp-field" aria-hidden="true"', msg_prefix=url)

    def test_messages_have_a_length_limit(self):
        self.client.post(reverse("core:submit_contact"), {"name": "Lise", "email": "l@x.ht", "message": "x" * 3001})
        self.assertFalse(ContactMessage.objects.exists())


class VisitCounterTests(TestCase):
    def test_counts_public_pages_by_name_without_cookie(self):
        r = self.client.get("/", **BROWSER)
        self.client.get("/", **BROWSER)
        self.assertNotIn("sessionid", r.cookies)
        self.assertEqual(PageView.objects.get(page="core:landing").views, 2)

    def test_invitation_link_is_never_stored(self):
        from events.models import Guest

        event = make_event(event_type="private")
        guest = Guest.objects.create(event=event, name="Carla")
        self.client.get(reverse("events:invitation", args=[guest.magic_token]), **BROWSER)
        pages = list(PageView.objects.values_list("page", flat=True))
        self.assertEqual(pages, ["events:invitation"])
        self.assertNotIn(str(guest.magic_token), "".join(pages))

    def test_robots_team_errors_and_redirects_are_not_counted(self):
        self.client.get("/", HTTP_USER_AGENT="Mozilla/5.0 (compatible; Googlebot/2.1)")
        self.client.get("/", HTTP_USER_AGENT="WhatsApp/2.23")
        self.client.get("/page-inconnue/", **BROWSER)
        self.client.get(reverse("accounts:guest_space"), **BROWSER)  # redirection vers la connexion
        self.assertFalse(PageView.objects.exists())
        admin = CustomUser.objects.create_user(username="a@x.ht", email="a@x.ht", password=PASSWORD, role="admin")
        self.client.force_login(admin)
        self.client.get("/", **BROWSER)
        self.client.get(reverse("dashboard:home"), **BROWSER)
        self.assertFalse(PageView.objects.exists())

    def test_dashboard_shows_the_counts(self):
        today = timezone.localdate()
        PageView.objects.create(day=today, page="core:landing", views=7)
        PageView.objects.create(day=today - timedelta(days=1), page="events:explore", views=3)
        PageView.objects.create(day=today - timedelta(days=60), page="core:landing", views=100)
        admin = CustomUser.objects.create_user(username="a@x.ht", email="a@x.ht", password=PASSWORD, role="admin")
        self.client.force_login(admin)
        r = self.client.get(reverse("dashboard:utm_report"))
        self.assertEqual((r.context["visits"]["today"], r.context["visits"]["total"]), (7, 10))
        self.assertContains(r, "Pages vues")
        self.assertContains(r, "<td>Accueil</td>", html=False)

    def test_privacy_page_mentions_the_counter(self):
        self.assertContains(self.client.get(reverse("core:privacy")), "nombre de pages vues")


class LightFilesTests(TestCase):
    def test_logo_files_are_light(self):
        for path in (BASE / "static/img/logo").glob("*.png"):
            self.assertLess(path.stat().st_size, 60_000, path.name)

    def test_site_photos_are_compressed(self):
        for path in (BASE / "static/img/photos").glob("*.jpg"):
            self.assertLess(path.stat().st_size, 250_000, path.name)
