"""Tests de solidité (docs/solidite.md) : limites, plafonds, erreurs, double paiement, pages, photos, cache, sauvegarde."""
import io
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import time, timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import CustomUser
from core import quotas
from core.models import HelpRequest
from core.views_errors import bad_request, server_error
from events.forms import EventForm
from events.geocoding import geocode_address
from events.models import Event, EventCategory, Guest
from payments.models import Contribution, Payment

PASSWORD = "MotDePasse-Solide-42"
KEY = "0123456789abcdef0123456789abcdef"


def make_user(email, role="guest", **extra):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, role=role, **extra)


def make_event(**kw):
    defaults = dict(title="Gala test", event_type="public", date=timezone.localdate() + timedelta(days=10),
                    time=time(19, 0), venue="Pétion-Ville", latitude=18.51, longitude=-72.28, max_guests=100)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def photo_bytes(size=(4000, 3000), fmt="JPEG", mode="RGB"):
    buffer = io.BytesIO()
    image = Image.new(mode, size, (120, 30, 140) if mode == "RGB" else (120, 30, 140, 0))
    if fmt == "JPEG":
        exif = Image.Exif()
        exif[0x010F] = "Téléphone de test"  # fabricant : doit disparaître
        image.save(buffer, fmt, exif=exif, quality=95)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 01. Limite de requêtes par visiteur
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLED=True)
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_login_is_blocked_after_ten_attempts(self):
        url = reverse("accounts:login")
        for _ in range(10):
            self.assertEqual(self.client.post(url, {"email": "x@x.ht", "password": "mauvais"}).status_code, 200)
        response = self.client.post(url, {"email": "x@x.ht", "password": "mauvais"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertContains(response, "Trop de demandes", status_code=429)
        # Afficher la page reste possible : seule l'envoi du formulaire est limité
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_each_visitor_has_its_own_counter(self):
        url = reverse("accounts:login")
        for _ in range(11):
            self.client.post(url, {"email": "x@x.ht", "password": "mauvais"})
        other = self.client_class(REMOTE_ADDR="10.0.0.2")
        self.assertEqual(other.post(url, {"email": "x@x.ht", "password": "mauvais"}).status_code, 200)

    def test_background_request_gets_a_json_answer(self):
        with override_settings(RATELIMIT_PER_MINUTE=2):
            self.client.get("/aide/")
            self.client.get("/aide/")
            response = self.client.get("/aide/", HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()["ok"])

    def test_general_limit_on_sent_forms(self):
        with override_settings(RATELIMIT_POSTS_PER_MINUTE=3):
            codes = [self.client.post(reverse("core:submit_review"), {}).status_code for _ in range(4)]
        self.assertEqual(codes[-1], 429)

    def test_logged_in_team_is_never_limited(self):
        self.client.force_login(make_user("equipe@x.ht", role="admin"))
        with override_settings(RATELIMIT_PER_MINUTE=2):
            codes = {self.client.get(reverse("dashboard:home")).status_code for _ in range(5)}
        self.assertEqual(codes, {200})

    def test_health_check_is_not_limited(self):
        with override_settings(RATELIMIT_PER_MINUTE=1):
            codes = {self.client.get("/sante/").status_code for _ in range(4)}
        self.assertEqual(codes, {200})

    def test_entry_code_guessing_is_limited(self):
        codes = [self.client.get(reverse("events:entry_code", args=[f"EL-AAAA-{i:04d}"])).status_code for i in range(31)]
        self.assertEqual(codes[-1], 429)

    def test_header_from_host_gives_the_real_visitor(self):
        url = reverse("accounts:login")
        with override_settings(REAL_IP_HEADER="HTTP_X_REAL_IP"):
            for _ in range(11):
                self.client.post(url, {"email": "x@x.ht", "password": "m"}, HTTP_X_REAL_IP="1.1.1.1")
            self.assertEqual(self.client.post(url, {"email": "x@x.ht", "password": "m"}, HTTP_X_REAL_IP="2.2.2.2").status_code, 200)


# ---------------------------------------------------------------------------
# 02 / 08. Plafond d'appels aux services extérieurs, services qui ne répondent pas
# ---------------------------------------------------------------------------
class QuotaTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_daily_limit(self):
        quotas.take("essai", 2)
        quotas.take("essai", 2)
        with self.assertLogs("eventlead.quotas", "ERROR"):
            with self.assertRaises(quotas.QuotaExceeded):
                quotas.take("essai", 2)

    @override_settings(EMAIL_DAILY_LIMIT=1, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_emails_stop_at_the_daily_limit(self):
        quotas.send_email(mail.EmailMessage("a", "b", to=["x@x.ht"]))
        with self.assertLogs("eventlead.quotas", "ERROR"), self.assertRaises(quotas.QuotaExceeded):
            quotas.send_email(mail.EmailMessage("a", "b", to=["y@x.ht"]))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_DAILY_LIMIT=0, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_reminder_says_the_email_will_leave_tomorrow(self):
        from events import reminders

        event = make_event(event_type="private")
        guest = Guest.objects.create(event=event, name="Rose", email="rose@x.ht", sent_via="email",
                                     invitation_sent_at=timezone.now() - timedelta(days=5))
        with self.assertLogs("eventlead.quotas", "ERROR"), self.assertRaisesMessage(reminders.ReminderError, "partira demain"):
            reminders.remind_guest(event, guest)
        self.assertFalse(guest.reminders.exists())

    def test_geocoding_is_remembered_and_capped(self):
        found = mock.Mock(latitude=18.5, longitude=-72.3)
        with mock.patch("geopy.geocoders.Nominatim.geocode", return_value=found) as call:
            self.assertEqual(geocode_address("Hôtel Montana, Pétion-Ville"), (18.5, -72.3))
            self.assertEqual(geocode_address("hôtel montana,  pétion-ville"), (18.5, -72.3))
            self.assertEqual(call.call_count, 1)
            with override_settings(GEOCODER_DAILY_LIMIT=1), self.assertLogs("eventlead.quotas", "ERROR"):
                self.assertIsNone(geocode_address("Cap-Haïtien"))
            self.assertEqual(call.call_count, 1)

    def test_geocoding_service_down_gives_no_map_but_no_crash(self):
        from geopy.exc import GeocoderTimedOut

        with mock.patch("geopy.geocoders.Nominatim.geocode", side_effect=GeocoderTimedOut("lent")):
            self.assertIsNone(geocode_address("Jacmel"))

    def test_timeouts_are_set(self):
        self.assertEqual(settings.EMAIL_TIMEOUT, 15)


# ---------------------------------------------------------------------------
# 04 / 17 / 18. Messages quand ça plante, santé du site, journal des erreurs
# ---------------------------------------------------------------------------
class ErrorPageTests(TestCase):
    def test_server_error_page_is_clear_and_needs_no_database(self):
        request = RequestFactory().get("/")
        with self.assertNumQueries(0):
            response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Un problème est survenu", response.content.decode())
        self.assertIn("Réessayer", response.content.decode())

    def test_bad_request_page(self):
        response = bad_request(RequestFactory().get("/"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("trop lourd", response.content.decode())

    def test_crash_in_a_view_shows_the_page_and_is_logged(self):
        self.client.raise_request_exception = False
        with mock.patch("core.views.render", side_effect=RuntimeError("panne simulée")):
            with self.assertLogs("django.request", "ERROR") as logs:
                response = self.client.get(reverse("core:landing"))
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Un problème est survenu", status_code=500)
        self.assertIn("panne simulée", "\n".join(logs.output))

    def test_errors_are_written_to_a_file_and_mailed(self):
        handlers = settings.LOGGING["loggers"]["django.request"]["handlers"]
        self.assertIn("mail_admins", handlers)
        self.assertIn("file", handlers)

    def test_health_check(self):
        response = self.client.get("/sante/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "base: ok")
        self.assertEqual(response["Cache-Control"], "no-store")
        with mock.patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor", side_effect=RuntimeError("base coupée")):
            with self.assertLogs("eventlead", "ERROR"):
                response = self.client.get("/sante/")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "base: erreur", status_code=503)

    def test_browser_errors_reach_the_log(self):
        with self.assertLogs("eventlead.browser", "WARNING") as logs:
            response = self.client.post(reverse("browser_error"), data=json.dumps({"message": "x is undefined"}),
                                        content_type="text/plain")
        self.assertEqual(response.status_code, 204)
        self.assertIn("x is undefined", logs.output[0])

    def test_pages_carry_the_loading_bar_and_network_messages(self):
        response = self.client.get(reverse("core:landing"))
        for text in ('id="el-loading"', 'id="el-net"', "data-msg-net-failed", "css/solidite.css"):
            self.assertContains(response, text)


# ---------------------------------------------------------------------------
# 09 / 10. Double clic, double paiement
# ---------------------------------------------------------------------------
class DoublePaymentTests(TestCase):
    def setUp(self):
        self.user = make_user("orga@x.ht", role="organizer")
        self.client.force_login(self.user)
        self.data = {"method": "moncash", "phone": "3712 3456", "otp": "123456", "idem": KEY}

    def test_form_carries_a_fresh_key_each_time(self):
        first = self.client.get(reverse("payments:vip")).content.decode()
        second = self.client.get(reverse("payments:vip")).content.decode()
        self.assertIn('name="idem"', first)
        key = lambda html: html.split('name="idem" value="')[1][:32]
        self.assertNotEqual(key(first), key(second))

    def test_double_click_on_vip_charges_once(self):
        first = self.client.post(reverse("payments:vip"), self.data)
        second = self.client.post(reverse("payments:vip"), self.data)
        self.assertEqual(Payment.objects.count(), 1)
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertRedirects(first, reverse("payments:success", args=[payment.reference]))
        self.assertEqual(second.status_code, 302)

    def test_double_click_on_ticket_charges_once(self):
        event = make_event(price_htg=1500)
        url = reverse("payments:checkout", args=[event.pk])
        self.client.post(url, {**self.data, "quantity": 2})
        response = self.client.post(url, {**self.data, "quantity": 2}, follow=True)
        self.assertEqual(Payment.objects.filter(kind=Payment.Kind.TICKET).count(), 1)
        self.assertContains(response, "déjà été effectué")

    def test_new_form_after_a_refused_payment_can_pay(self):
        url = reverse("payments:vip")
        self.client.post(url, {**self.data, "otp": "000000"})
        self.client.post(url, {**self.data, "idem": "f" * 32})
        self.assertEqual(list(Payment.objects.order_by("pk").values_list("status", flat=True)),
                         [Payment.Status.FAILED, Payment.Status.SUCCESS])

    def test_payment_service_down_is_refused_cleanly(self):
        with mock.patch("payments.idempotency.charge", side_effect=TimeoutError("pas de réponse")):
            with self.assertLogs("eventlead.payments", "ERROR"):
                response = self.client.post(reverse("payments:vip"), self.data, follow=True)
        self.assertContains(response, "ne répond pas")
        self.assertEqual(Payment.objects.get().status, Payment.Status.FAILED)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_vip)

    def test_double_click_on_contribution_charges_once(self):
        event = make_event(event_type="private", accept_contributions=True)
        guest = Guest.objects.create(event=event, name="Carla", phone="+509 3712 3456")
        self.client.logout()
        self.client.post(reverse("events:invitation", args=[guest.magic_token]), {"status": "confirmed", "companions": 0})
        url = reverse("events:invitation_contribution", args=[guest.magic_token])
        data = {"method": "moncash", "amount": 2500, "message": "", "phone": "3712 3456", "otp": "123456", "idem": KEY}
        self.client.post(url, data)
        self.client.post(url, data)
        self.assertEqual(Payment.objects.filter(kind=Payment.Kind.CONTRIBUTION).count(), 1)
        self.assertEqual(Contribution.objects.count(), 1)


# ---------------------------------------------------------------------------
# 11 / 12 / 13. Données chargées, index, pages
# ---------------------------------------------------------------------------
class ListTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@x.ht", role="admin")
        self.client.force_login(self.admin)
        self.event = make_event(event_type="private")
        Guest.objects.bulk_create([Guest(event=self.event, name=f"Invité {i:03d}", entry_code=f"EL-T{i:03d}-0000") for i in range(60)])

    def test_guest_list_is_cut_into_pages(self):
        response = self.client.get(reverse("dashboard:guest_list"), {"event": self.event.pk})
        self.assertEqual(len(response.context["guests"]), 50)
        self.assertContains(response, "1 à 50 sur 60")
        self.assertContains(response, f"?event={self.event.pk}&amp;page=2")  # le filtre est gardé
        page2 = self.client.get(reverse("dashboard:guest_list"), {"event": self.event.pk, "page": 2})
        self.assertEqual(len(page2.context["guests"]), 10)
        self.assertEqual(self.client.get(reverse("dashboard:guest_list"), {"page": "abc"}).status_code, 200)
        self.assertEqual(len(self.client.get(reverse("dashboard:guest_list"), {"page": 999}).context["guests"]), 10)

    def test_other_long_lists_have_pages(self):
        HelpRequest.objects.bulk_create([HelpRequest(name="A", contact="a@x.ht", message="m") for _ in range(35)])
        self.assertEqual(len(self.client.get(reverse("dashboard:help_list")).context["help_requests"]), 30)
        for name in ("dashboard:event_list", "dashboard:payment_history", "dashboard:inbox", "dashboard:ad_list",
                     "events:explore", "payments:ticketing"):
            self.assertIn("page_obj", self.client.get(reverse(name)).context, name)

    def test_organizer_portal_does_not_query_once_per_event(self):
        vip = make_user("vip@x.ht", role="organizer", is_vip=True)
        self.client.force_login(vip)
        for i in range(3):
            make_event(title=f"Public {i}")
        self.client.get(reverse("events:organizer_portal"))
        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse("events:organizer_portal"))
        for i in range(6):
            make_event(title=f"Autre {i}")
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("events:organizer_portal"))
        self.assertEqual(len(few), len(many))

    def test_search_indexes_exist(self):
        names = {index.name for index in Event._meta.indexes} | {index.name for index in Guest._meta.indexes} | \
            {index.name for index in Payment._meta.indexes}
        for name in ("event_public_upcoming_idx", "guest_event_status_idx", "payment_status_created_idx"):
            self.assertIn(name, names)

    def test_no_missing_migration(self):
        out = io.StringIO()
        call_command("makemigrations", check=True, dry_run=True, stdout=out)


# ---------------------------------------------------------------------------
# 14 / 15. Fichiers envoyés : compressés, poids limité
# ---------------------------------------------------------------------------
class UploadTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def form(self, **files):
        data = {"title": "Gala", "event_type": "public", "status": "active", "date": "2030-01-10", "time": "19:00",
                "venue": "Pétion-Ville", "latitude": "18.5", "longitude": "-72.3", "max_guests": 50,
                "max_companions": 0, "evaluation_delay_days": 1}
        return EventForm(data, files)

    def test_cover_photo_is_resized_and_stripped(self):
        raw = photo_bytes()
        form = self.form(cover_image=SimpleUploadedFile("IMG_0001.JPG", raw, content_type="image/jpeg"))
        self.assertTrue(form.is_valid(), form.errors)
        event = form.save()
        with Image.open(event.cover_image.path) as saved:
            self.assertLessEqual(max(saved.size), 1920)
            self.assertEqual(saved.format, "JPEG")
            self.assertNotIn(0x010F, saved.getexif())
        self.assertLess(event.cover_image.size, len(raw))

    def test_transparent_logo_stays_png(self):
        from core.uploads import compress_photo

        result = compress_photo(SimpleUploadedFile("logo.png", photo_bytes((800, 400), "PNG", "RGBA"), content_type="image/png"))
        self.assertTrue(result.name.endswith(".png"))

    def test_fake_photo_and_heavy_files_are_refused(self):
        form = self.form(cover_image=SimpleUploadedFile("virus.jpg", b"pas une image", content_type="image/jpeg"))
        self.assertFalse(form.is_valid())
        heavy = SimpleUploadedFile("lourde.jpg", photo_bytes((400, 300)), content_type="image/jpeg")
        heavy.size = 12 * 1024 * 1024 + 1
        form = self.form(cover_image=heavy)
        self.assertFalse(form.is_valid())
        self.assertIn("trop lourde", str(form.errors))

    def test_video_rules(self):
        form = self.form(cover_video=SimpleUploadedFile("clip.exe", b"x", content_type="application/octet-stream"))
        self.assertFalse(form.is_valid())
        big = SimpleUploadedFile("clip.mp4", b"0" * 10, content_type="video/mp4")
        big.size = 41 * 1024 * 1024
        form = self.form(cover_video=big)
        self.assertFalse(form.is_valid())
        self.assertIn("40 Mo", str(form.errors))
        self.assertTrue(self.form(cover_video=SimpleUploadedFile("clip.mp4", b"0" * 10, content_type="video/mp4")).is_valid())

    def test_request_size_limits(self):
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES, 25)


# ---------------------------------------------------------------------------
# 16. Ce qui ne change pas, gardé en mémoire
# ---------------------------------------------------------------------------
@override_settings(CONTENT_CACHE_SECONDS=300)
class ContentCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        make_event(title="Concert du soir")

    def tearDown(self):
        cache.clear()

    def test_home_page_reads_the_database_once_then_memory(self):
        self.client.get(reverse("core:landing"))
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("core:landing"))
        self.assertEqual(len(queries), 0)

    def test_a_change_is_visible_at_once(self):
        self.client.get(reverse("core:landing"))
        make_event(title="Gala de la Saint-Valentin")
        self.assertContains(self.client.get(reverse("core:landing")), "Gala de la Saint-Valentin")
        EventCategory.objects.create(name="Baby shower")
        self.assertContains(self.client.get(reverse("core:landing")), "Baby shower")


# ---------------------------------------------------------------------------
# 20. La sauvegarde se restaure
# ---------------------------------------------------------------------------
class BackupTests(TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.media = Path(tempfile.mkdtemp())
        (self.media / "albums").mkdir()
        (self.media / "albums" / "photo.jpg").write_bytes(photo_bytes((40, 30)))
        self.override = override_settings(BACKUP_DIR=self.folder, MEDIA_ROOT=self.media)
        self.override.enable()
        event = make_event()
        Guest.objects.create(event=event, name="Nadège", email="nadege@x.ht")
        make_user("nadege@x.ht")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.media, ignore_errors=True)

    def backup(self):
        call_command("sauvegarder", stdout=io.StringIO())
        return sorted(self.folder.glob("eventlead-*.zip"))[-1]

    def test_backup_restores_with_every_row_and_photo(self):
        path = self.backup()
        before = (Guest.objects.count(), Guest.objects.get().user_id)
        out = io.StringIO()
        call_command("verifier_sauvegarde", str(path), stdout=out)
        self.assertIn("Sauvegarde valide", out.getvalue())
        self.assertIn("1 fichiers médias", out.getvalue())
        self.assertEqual((Guest.objects.count(), Guest.objects.get().user_id), before)  # la vraie base n'a pas bougé

    def test_damaged_backup_is_detected(self):
        path = self.backup()
        broken = self.folder / "eventlead-abimee.zip"
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(broken, "w") as target:
            manifest = json.loads(source.read("manifest.json"))
            manifest["counts"]["events.guest"] += 1
            target.writestr("manifest.json", json.dumps(manifest))
            target.writestr("data.json", source.read("data.json"))
        with self.assertRaisesMessage(CommandError, "NE se restaure PAS"):
            call_command("verifier_sauvegarde", str(broken), stdout=io.StringIO())

    def test_old_backups_are_cleaned(self):
        for i in range(3):
            (self.folder / f"eventlead-2020010{i}-000000.zip").write_bytes(b"")
        call_command("sauvegarder", "--garder", "2", stdout=io.StringIO())
        self.assertEqual(len(list(self.folder.glob("eventlead-*.zip"))), 2)
