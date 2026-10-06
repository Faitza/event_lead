"""Logo sans fond blanc et versions en couleur programmées par dates (Tableau de bord > Logo)."""
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from core.models import LogoVariant

BASE = Path(settings.BASE_DIR)
TODAY = timezone.localdate()


class LogoVariantTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(username="a@x.ht", email="a@x.ht", password="Mot-de-passe-2026", role="admin")

    def test_every_ready_color_has_two_files(self):
        for value, _label in LogoVariant.Preset.choices:
            if value == "perso":
                continue
            for suffix in ("", "-sombre"):
                self.assertTrue((BASE / f"static/img/logo/eventlead-{value}{suffix}.png").exists(), value + suffix)

    def test_original_logo_without_white_box_by_default(self):
        html = self.client.get(reverse("core:landing")).content.decode()
        self.assertIn("img/logo/eventlead-original.png", html)
        self.assertIn("img/logo/eventlead-original-sombre.png", html)
        css = (BASE / "static/css/eventlead.css").read_text(encoding="utf-8")
        self.assertNotIn(".auth-panel > a { background: #fff", css)
        self.assertNotIn("footer-badge { display: inline-flex; background: #fff", css)

    def test_color_shows_only_between_its_dates(self):
        LogoVariant.objects.create(name="Noël", preset="rouge", start_date=TODAY - timedelta(days=1), end_date=TODAY + timedelta(days=1))
        LogoVariant.objects.create(name="Plus tard", preset="bleu", start_date=TODAY + timedelta(days=5), end_date=TODAY + timedelta(days=9))
        html = self.client.get(reverse("core:landing")).content.decode()
        self.assertIn("img/logo/eventlead-rouge.png", html)
        self.assertIn("img/logo/eventlead-rouge-sombre.png", html)
        self.assertNotIn("eventlead-bleu", html)
        self.assertEqual(LogoVariant.current(TODAY + timedelta(days=6)).name, "Plus tard")
        self.assertIsNone(LogoVariant.current(TODAY + timedelta(days=3)))

    def test_disabled_color_is_ignored(self):
        LogoVariant.objects.create(name="Off", preset="or", start_date=TODAY, end_date=TODAY, is_active=False)
        self.assertNotIn("eventlead-or.png", self.client.get(reverse("core:landing")).content.decode())

    def test_team_programs_a_color(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("dashboard:logo_list")), "Couleurs prêtes")
        r = self.client.post(reverse("dashboard:logo_create"), {
            "name": "Saint-Valentin", "preset": "rose", "start_date": TODAY.isoformat(),
            "end_date": (TODAY + timedelta(days=3)).isoformat(), "is_active": "on",
        })
        self.assertRedirects(r, reverse("dashboard:logo_list"))
        self.assertIn("eventlead-rose.png", self.client.get(reverse("core:landing")).content.decode())

    def test_end_before_start_and_custom_without_file_are_refused(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("dashboard:logo_create"), {
            "name": "X", "preset": "perso", "start_date": TODAY.isoformat(), "end_date": (TODAY - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("end_date", r.context["form"].errors)
        self.assertIn("image", r.context["form"].errors)
        self.assertFalse(LogoVariant.objects.exists())

    def test_delete_brings_back_the_original(self):
        v = LogoVariant.objects.create(name="Noël", preset="rouge", start_date=TODAY, end_date=TODAY)
        self.client.force_login(self.admin)
        self.client.post(reverse("dashboard:logo_delete", args=[v.pk]))
        self.assertIn("eventlead-original.png", self.client.get(reverse("core:landing")).content.decode())

    def test_logo_pages_are_for_the_team_only(self):
        self.assertEqual(self.client.get(reverse("dashboard:logo_list")).status_code, 302)
