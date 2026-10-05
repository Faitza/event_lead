"""Publicités en vidéo : fichier envoyé ou lien YouTube / Facebook, joués sans le son avec l'image en affiche."""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests import make_event, make_user
from events.models import Guest

from .forms import AdForm
from .models import Ad, youtube_id

MEDIA = tempfile.mkdtemp()


def form_data(**extra):
    data = {"title": "Traiteur", "icon_name": "bi-megaphone", "message": "Buffet", "sponsor_link": "https://example.com",
            "skip_after_seconds": 5, "is_active": True, "show_after_reply": True, "order": 0}
    data.update(extra)
    return data


@override_settings(MEDIA_ROOT=MEDIA)
class AdVideoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_youtube_links_are_recognised(self):
        for url in ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ",
                    "https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=3"):
            self.assertEqual(youtube_id(url), "dQw4w9WgXcQ", url)
        self.assertEqual(youtube_id("https://evil.example/watch?v=dQw4w9WgXcQ"), "")

    def test_embed_is_muted_autoplay_loop(self):
        ad = Ad(title="t", message="m", sponsor_link="https://example.com", video_url="https://youtu.be/dQw4w9WgXcQ")
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ?autoplay=1&mute=1&loop=1", ad.video_embed_url)
        ad.video_url = "https://www.facebook.com/page/videos/123456/"
        self.assertTrue(ad.video_embed_url.startswith("https://www.facebook.com/plugins/video.php?href=https%3A%2F%2F"))
        self.assertIn("mute=true", ad.video_embed_url)
        self.assertTrue(ad.has_video)

    def test_form_refuses_other_links_and_files(self):
        form = AdForm(form_data(video_url="https://vimeo.com/123"))
        self.assertIn("video_url", form.errors)
        form = AdForm(form_data(), {"video": SimpleUploadedFile("pub.exe", b"x", content_type="application/octet-stream")})
        self.assertIn("video", form.errors)
        self.assertTrue(AdForm(form_data(video_url="https://youtu.be/dQw4w9WgXcQ")).is_valid())

    def test_admin_can_add_a_video_ad(self):
        self.client.force_login(make_user("adm@x.ht", role="admin"))
        clip = SimpleUploadedFile("clip.mp4", b"0" * 20, content_type="video/mp4")
        r = self.client.post(reverse("dashboard:ad_create"), {**form_data(), "video": clip})
        self.assertEqual(r.status_code, 302)
        ad = Ad.objects.get()
        self.assertTrue(ad.video.name.endswith(".mp4"))
        self.assertContains(self.client.get(reverse("dashboard:ad_list")), "Vidéo")

    def test_video_plays_muted_in_parade_and_on_ad_page(self):
        ad = Ad.objects.create(title="Traiteur vidéo", message="m", sponsor_link="https://example.com",
                               video=SimpleUploadedFile("clip.mp4", b"0" * 20, content_type="video/mp4"))
        landing = self.client.get(reverse("core:landing"))
        self.assertContains(landing, 'class="ad-video"')
        self.assertContains(landing, "autoplay muted loop playsinline")
        self.assertContains(landing, 'id="parade-toggle"')
        guest = Guest.objects.create(event=make_event(), name="Carla", phone="+509 3712 3456")
        page = self.client.get(reverse("events:invitation_ad", args=[guest.magic_token, ad.pk]))
        self.assertContains(page, "autoplay muted loop playsinline preload=\"metadata\" controls")
        self.assertContains(self.client.get(reverse("ads:list")), 'class="ad-video"')

    def test_youtube_ad_in_parade_keeps_link_outside_player(self):
        Ad.objects.create(title="Fleuriste", message="m", sponsor_link="https://example.com",
                          video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        r = self.client.get(reverse("core:landing"))
        self.assertContains(r, "ad-embed no-touch")
        self.assertContains(r, '<div class="p-card p-ad">')

    def test_image_only_ad_unchanged(self):
        Ad.objects.create(title="Pâtisserie", message="m", sponsor_link="https://example.com")
        r = self.client.get(reverse("core:landing"))
        self.assertNotContains(r, "<video")
        self.assertNotContains(r, "<iframe")
