"""Tests des tuiles « Pour chaque occasion » de l'accueil : une tuile par catégorie, photo modifiable par l'équipe."""
import importlib.util
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.defaultfilters import slugify
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image

from core.test_thanks import MEDIA, PASSWORD, image_file, make_event, make_user
from events import album
from events.models import DEFAULT_CATEGORIES, EventCategory


@override_settings(MEDIA_ROOT=MEDIA)
class OccasionTileTests(TestCase):
    def setUp(self):
        translation.activate("fr")
        self.addCleanup(translation.deactivate)
        # Les tests ne dépendent pas des photos par défaut réellement présentes dans static/img/categories/
        patcher = mock.patch("events.models.finders.find", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.birthday = EventCategory.objects.create(name="Anniversaire", icon_name="bi-balloon", order=1)
        self.baby = EventCategory.objects.create(name="Baby shower", icon_name="bi-balloon-heart", order=2)
        self.gala = EventCategory.objects.create(name="Gala", icon_name="bi-stars", order=3)
        make_event(title="Grand gala", event_type="public", category=self.gala, date=timezone.localdate() + timedelta(days=20))
        self.admin = make_user("adm@x.ht", role="admin")

    def tiles(self, html):
        block = html.split('class="occasion-grid"')[1].split('class="service-grid"')[0]
        return block.split('class="occasion"')[1:]

    def test_one_tile_per_category_in_order(self):
        html = self.client.get(reverse("core:landing")).content.decode()
        tiles = self.tiles(html)
        self.assertEqual(len(tiles), 3)
        self.assertIn("Anniversaire", tiles[0])
        self.assertIn("Baby shower", tiles[1])
        self.assertIn("Gala", tiles[2])

    def test_tile_without_photo_shows_the_placeholder_with_the_icon(self):
        tile = self.tiles(self.client.get(reverse("core:landing")).content.decode())[1]
        self.assertIn('class="occasion-ph"', tile)
        self.assertIn("bi-balloon-heart", tile)
        self.assertNotIn("<img", tile)

    def test_tile_uses_the_site_default_photo_when_the_team_added_none(self):
        with mock.patch("events.models.finders.find", return_value="/x/img/categories/baby-shower.jpg"):
            tile = self.tiles(self.client.get(reverse("core:landing")).content.decode())[1]
        self.assertIn("img/categories/baby-shower.jpg", tile)
        self.assertNotIn('class="occasion-ph"', tile)

    def test_team_photo_wins_over_the_site_default_photo(self):
        self.client.login(username="adm@x.ht", password=PASSWORD)
        self.client.post(reverse("dashboard:category_edit", args=[self.baby.pk]), {
            "name": "Baby shower", "icon_name": "bi-balloon-heart", "order": 2, "image": image_file(size=(1200, 900)),
        })
        self.baby.refresh_from_db()
        with mock.patch("events.models.finders.find", return_value="/x/img/categories/baby-shower.jpg"):
            tile = self.tiles(self.client.get(reverse("core:landing")).content.decode())[1]
        self.assertIn(self.baby.image.url, tile)
        self.assertNotIn("img/categories/baby-shower.jpg", tile)

    def test_default_photo_is_looked_up_by_the_category_identifier(self):
        looked_up = []
        with mock.patch("events.models.finders.find", side_effect=lambda path: looked_up.append(path)):
            self.assertEqual(self.baby.tile_url, "")
        self.assertEqual(looked_up, ["img/categories/baby-shower.jpg"])

    def test_tile_links_to_events_only_when_the_category_has_upcoming_ones(self):
        tiles = self.tiles(self.client.get(reverse("core:landing")).content.decode())
        self.assertIn('href="#contact"', tiles[0])
        self.assertIn('href="%s?categorie=gala"' % reverse("events:explore"), tiles[2])

    def test_no_categories_no_block(self):
        EventCategory.objects.all().delete()
        html = self.client.get(reverse("core:landing")).content.decode()
        self.assertNotIn("occasion-grid", html)

    def test_tile_shows_the_photo_once_uploaded(self):
        self.client.login(username="adm@x.ht", password=PASSWORD)
        r = self.client.post(reverse("dashboard:category_edit", args=[self.baby.pk]), {
            "name": "Baby shower", "icon_name": "bi-balloon-heart", "order": 2, "image": image_file(size=(1600, 900)),
        })
        self.assertRedirects(r, reverse("dashboard:category_list"))
        self.baby.refresh_from_db()
        self.assertTrue(self.baby.image)
        tile = self.tiles(self.client.get(reverse("core:landing")).content.decode())[1]
        self.assertIn(self.baby.image.url, tile)
        self.assertNotIn('class="occasion-ph"', tile)

    def test_uploaded_photo_is_cropped_to_4_3_jpeg(self):
        tile = album.tile_photo(image_file(size=(2000, 800), fmt="PNG"))
        with Image.open(tile) as image:
            self.assertEqual(image.size, album.TILE_SIZE)
            self.assertEqual(image.format, "JPEG")

    def test_too_small_or_invalid_photo_is_refused_with_a_message(self):
        self.client.login(username="adm@x.ht", password=PASSWORD)
        url = reverse("dashboard:category_edit", args=[self.baby.pk])
        data = {"name": "Baby shower", "icon_name": "bi-balloon-heart", "order": 2}
        small = self.client.post(url, {**data, "image": image_file(size=(200, 100))})
        self.assertContains(small, "trop petite")
        fake = self.client.post(url, {**data, "image": SimpleUploadedFile("x.jpg", b"pas une image", content_type="image/jpeg")})
        self.assertEqual(fake.status_code, 200)
        self.baby.refresh_from_db()
        self.assertFalse(self.baby.image)

    def test_replacing_or_removing_the_photo_deletes_the_old_file(self):
        self.client.login(username="adm@x.ht", password=PASSWORD)
        url = reverse("dashboard:category_edit", args=[self.baby.pk])
        data = {"name": "Baby shower", "icon_name": "bi-balloon-heart", "order": 2}
        self.client.post(url, {**data, "image": image_file(size=(1200, 900))})
        self.baby.refresh_from_db()
        first = self.baby.image.path
        self.assertTrue(os.path.exists(first))
        self.client.post(url, {**data, "image": image_file(size=(1200, 900))})
        self.baby.refresh_from_db()
        second = self.baby.image.path
        self.assertNotEqual(first, second)
        self.assertFalse(os.path.exists(first))
        self.client.post(url, {**data, "remove_image": "on"})
        self.baby.refresh_from_db()
        self.assertFalse(self.baby.image)
        self.assertFalse(os.path.exists(second))

    def test_saving_without_a_new_file_keeps_the_photo(self):
        self.client.login(username="adm@x.ht", password=PASSWORD)
        url = reverse("dashboard:category_edit", args=[self.baby.pk])
        data = {"name": "Baby shower", "icon_name": "bi-balloon-heart", "order": 2}
        self.client.post(url, {**data, "image": image_file(size=(1200, 900))})
        self.baby.refresh_from_db()
        name = self.baby.image.name
        self.client.post(url, {**{**data, "order": 5}})
        self.baby.refresh_from_db()
        self.assertEqual(self.baby.image.name, name)
        self.assertEqual(self.baby.order, 5)

    def test_only_admins_can_change_a_photo(self):
        make_user("guest@x.ht")
        self.client.login(username="guest@x.ht", password=PASSWORD)
        r = self.client.post(reverse("dashboard:category_edit", args=[self.baby.pk]), {
            "name": "Baby shower", "icon_name": "bi-balloon-heart", "order": 2, "image": image_file(size=(1200, 900)),
        })
        self.assertEqual(r.status_code, 403)


class DefaultCategoriesTests(TestCase):
    def setUp(self):
        translation.activate("fr")
        self.addCleanup(translation.deactivate)
        self.admin = make_user("adm@x.ht", role="admin")
        self.client.login(username="adm@x.ht", password=PASSWORD)

    def test_defaults_include_baby_shower_and_start_with_birthday_wedding(self):
        names = [name for name, icon in DEFAULT_CATEGORIES]
        self.assertEqual(names[:3], ["Anniversaire", "Mariage", "Baby shower"])

    def test_button_adds_only_the_missing_defaults_after_the_existing_ones(self):
        EventCategory.objects.create(name="Mariage", icon_name="bi-heart", order=4)
        page = self.client.get(reverse("dashboard:category_list"))
        self.assertContains(page, "Ajouter les catégories par défaut")
        self.client.post(reverse("dashboard:category_add_defaults"))
        names = list(EventCategory.objects.order_by("order").values_list("name", flat=True))
        self.assertEqual(names[0], "Mariage")
        self.assertEqual(sorted(names), sorted(name for name, icon in DEFAULT_CATEGORIES))
        self.assertEqual(EventCategory.objects.filter(name__iexact="mariage").count(), 1)
        self.assertNotContains(self.client.get(reverse("dashboard:category_list")), "Ajouter les catégories par défaut")

    def test_button_is_post_only(self):
        self.assertEqual(self.client.get(reverse("dashboard:category_add_defaults")).status_code, 405)


class DeliveredTilePhotosTests(TestCase):
    """Chaque catégorie par défaut a sa photo livrée avec le site (static/img/categories/<identifiant>.jpg)."""

    def test_every_default_category_has_a_4_3_photo_of_a_readable_size(self):
        for name, icon in DEFAULT_CATEGORIES:
            slug = slugify(name)
            path = finders.find("img/categories/%s.jpg" % slug)
            self.assertTrue(path, "photo manquante pour %s (static/img/categories/%s.jpg)" % (name, slug))
            with Image.open(path) as photo:
                self.assertEqual(photo.format, "JPEG", slug)
                self.assertGreaterEqual(photo.width, 480, slug)
                self.assertGreaterEqual(photo.height, 360, slug)
                self.assertAlmostEqual(photo.width / photo.height, 4 / 3, delta=0.01, msg=slug)

    def test_every_delivered_photo_is_noted_in_the_credits_file(self):
        credits = (Path(settings.BASE_DIR) / "docs" / "credits-photos.md").read_text(encoding="utf-8")
        for name, icon in DEFAULT_CATEGORIES:
            self.assertIn("static/img/categories/%s.jpg" % slugify(name), credits)

    def test_a_default_category_created_without_photo_gets_the_delivered_one_on_the_landing(self):
        translation.activate("fr")
        self.addCleanup(translation.deactivate)
        for order, (name, icon) in enumerate(DEFAULT_CATEGORIES, start=1):
            EventCategory.objects.create(name=name, icon_name=icon, order=order)
        html = self.client.get(reverse("core:landing")).content.decode()
        self.assertNotIn('class="occasion-ph"', html)
        for name, icon in DEFAULT_CATEGORIES:
            self.assertIn("img/categories/%s.jpg" % slugify(name), html)


class CategoryPhotoToolTests(SimpleTestCase):
    """tools/set_category_photo.py : cadre 4:3 autour du point à garder, jamais d'agrandissement."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spec = importlib.util.spec_from_file_location("set_category_photo", Path(settings.BASE_DIR) / "tools" / "set_category_photo.py")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def run_tool(self, source_size, *extra, color=(200, 30, 30)):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        source = Path(tmp) / "source.png"
        Image.new("RGB", source_size, color).save(source)
        out, credits = Path(tmp) / "out", Path(tmp) / "credits.md"
        argv = ["set_category_photo.py", "mariage", str(source), "--licence", "Photo du client", *extra]
        with mock.patch.object(self.tool, "ROOT", Path(tmp)), mock.patch.object(self.tool, "OUT_DIR", out), \
                mock.patch.object(self.tool, "CREDITS", credits), mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"):
            self.tool.main()
        with Image.open(out / "mariage.jpg") as result:
            return result.size, credits.read_text(encoding="utf-8")

    def test_big_photo_is_reduced_to_960_by_720(self):
        size, _ = self.run_tool((2400, 3000))
        self.assertEqual(size, (960, 720))

    def test_small_photo_is_not_enlarged(self):
        size, _ = self.run_tool((563, 658))
        self.assertEqual(size, (563, 422))

    def test_zoom_gives_a_tighter_frame_without_enlarging(self):
        size, _ = self.run_tool((960, 1280), "--zoom", "1.5")
        self.assertEqual(size, (640, 480))

    def test_too_small_after_framing_is_refused(self):
        with self.assertRaises(SystemExit):
            self.run_tool((960, 1280), "--zoom", "2.5")

    def test_focus_chooses_which_part_of_a_tall_photo_is_kept(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        source = Path(tmp) / "source.png"
        tall = Image.new("RGB", (800, 1600), (255, 255, 255))
        tall.paste(Image.new("RGB", (800, 200), (255, 0, 0)), (0, 0))      # haut rouge
        tall.paste(Image.new("RGB", (800, 200), (0, 0, 255)), (0, 1400))   # bas bleu
        tall.save(source)
        out = Path(tmp) / "out"
        for focus, expected in (("0.5,0", (255, 0, 0)), ("0.5,1", (0, 0, 255))):
            argv = ["set_category_photo.py", "gala", str(source), "--licence", "x", "--focus", focus]
            with mock.patch.object(self.tool, "ROOT", Path(tmp)), mock.patch.object(self.tool, "OUT_DIR", out), \
                    mock.patch.object(self.tool, "CREDITS", Path(tmp) / "c.md"), mock.patch.object(sys, "argv", argv), \
                    mock.patch("builtins.print"):
                self.tool.main()
            with Image.open(out / "gala.jpg") as result:
                red, green, blue = result.convert("RGB").getpixel((400, 20 if focus.endswith("0") else result.height - 20))
            self.assertTrue(all(abs(a - b) < 40 for a, b in zip((red, green, blue), expected)), (focus, (red, green, blue)))

    def test_note_is_added_to_the_credits_line(self):
        _, credits = self.run_tool((1200, 900), "--note", "filigrane du photographe")
        self.assertIn("Photo du client (filigrane du photographe)", credits)


class NavbarMoreMenuTests(TestCase):
    """Le haut de page garde les liens essentiels visibles et regroupe les autres dans « Plus »."""

    def setUp(self):
        translation.activate("fr")
        self.addCleanup(translation.deactivate)

    def header(self, url):
        html = self.client.get(url).content.decode()
        return html.split('<header class="el-nav')[1].split("</header>")[0]

    def test_essential_links_stay_visible_and_the_others_are_in_the_menu(self):
        header = self.header(reverse("core:landing"))
        menu = header.split('class="dropdown-menu nav-more"')[1].split("</ul>")[0]
        for label in ("À propos", "Contact", "Aide"):
            self.assertIn(label, menu)
        visible = header.split('class="nav-item dropdown"')[0]
        for label in ("Accueil", "Événements", "Billetterie", "Services"):
            self.assertIn(label, visible)
        for label in ("À propos", "Contact", "Aide"):
            self.assertNotIn(">%s<" % label, visible)

    def test_menu_is_marked_active_on_the_help_page(self):
        header = self.header(reverse("core:help"))
        self.assertIn('dropdown-toggle active', header)
        self.assertIn('dropdown-item active', header)

    def test_menu_label_is_translated(self):
        for lang, label in (("en", "More"), ("ht", "Plis")):
            html = self.client.get(reverse("core:landing"), HTTP_ACCEPT_LANGUAGE=lang).content.decode()
            self.assertIn(">%s</button>" % label, html.split('<header class="el-nav')[1])


class StaticVersionTests(TestCase):
    def test_stylesheet_and_script_urls_carry_a_version_number(self):
        html = self.client.get(reverse("core:landing")).content.decode()
        self.assertRegex(html, r'css/eventlead\.css\?v=\d+')
        self.assertRegex(html, r'js/eventlead\.js\?v=\d+')

    def test_unknown_file_gives_a_plain_url(self):
        from core.templatetags.el_tags import static_v
        self.assertNotIn("?v=", static_v("css/n-existe-pas.css"))
