"""Tests des remerciements et de l'album : photos contrôlées, page « Merci » réservée aux présents, envoi WhatsApp ou e-mail."""
import io
import os
import tempfile
import zipfile
from datetime import time, timedelta
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.html import escape
from PIL import Image

from accounts.models import CustomUser
from events import album, thanks
from events.forms import EventForm
from events.models import AlbumPhoto, Event, Guest
from gifts.models import Gift, GiftClaim

PASSWORD = "MotDePasse-Solide-42"
MEDIA = tempfile.mkdtemp(prefix="eventlead-test-media-")


def make_event(**kw):
    defaults = dict(title="Anniversaire de Mme Duval", event_type="private", date=timezone.localdate() - timedelta(days=3),
                    time=time(18, 0), venue="Pétion-Ville", max_guests=100)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def make_guest(event, name="Nadège Louis", status="confirmed", **kw):
    defaults = dict(event=event, name=name, email="nadege@example.com", phone="+509 3712 3456", sent_via="email", status=status,
                    replied_at=timezone.now() - timedelta(days=10))
    defaults.update(kw)
    return Guest.objects.create(**defaults)


def make_user(email, role="guest"):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, role=role)


def image_file(name="photo.jpg", size=(800, 600), fmt="JPEG", mode="RGB", **save_kw):
    buffer = io.BytesIO()
    Image.new(mode, size, (200, 80, 120) if mode == "RGB" else (200, 80, 120, 128)).save(buffer, fmt, **save_kw)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=MEDIA)
class AlbumTests(TestCase):
    def setUp(self):
        translation.activate("fr")  # le service parle la langue active : on ne dépend pas d'un test précédent
        self.addCleanup(translation.deactivate)
        self.event = make_event()
        self.guest = make_guest(self.event)

    def test_photo_is_resized_and_gets_a_thumbnail(self):
        added, errors = album.add_photos(self.event, [image_file(size=(4000, 3000))])
        self.assertEqual((added, errors), (1, []))
        photo = self.event.photos.get()
        self.assertIsNone(photo.guest)
        full, thumb = Image.open(photo.image.path), Image.open(photo.thumb.path)
        self.assertEqual((full.format, max(full.size)), ("JPEG", album.FULL_SIDE))
        self.assertEqual((thumb.format, max(thumb.size)), ("JPEG", album.THUMB_SIDE))

    def test_file_names_cannot_be_guessed(self):
        album.add_photos(self.event, [image_file("IMG_0001.jpg")])
        name = os.path.basename(self.event.photos.get().image.name)
        self.assertNotIn("IMG_0001", name)
        self.assertGreaterEqual(len(os.path.splitext(name)[0]), 32)

    def test_rotation_is_applied_and_metadata_removed(self):
        exif = Image.Exif()
        exif[274] = 6  # photo prise téléphone couché : à tourner
        exif[306] = "2026:10:03 18:00:00"
        album.add_photos(self.event, [image_file(size=(800, 400), exif=exif.tobytes())])
        stored = Image.open(self.event.photos.get().image.path)
        self.assertGreater(stored.height, stored.width)
        self.assertEqual(len(stored.getexif()), 0)

    def test_png_with_transparency_and_webp_are_accepted(self):
        added, errors = album.add_photos(self.event, [image_file("a.png", fmt="PNG", mode="RGBA"), image_file("b.webp", fmt="WEBP")])
        self.assertEqual((added, errors), (2, []))
        for photo in self.event.photos.all():
            self.assertEqual(Image.open(photo.image.path).mode, "RGB")

    def test_what_is_not_a_photo_is_refused_without_blocking_the_others(self):
        fake = SimpleUploadedFile("virus.jpg", b"not an image at all", content_type="image/jpeg")
        gif = image_file("anim.gif", fmt="GIF", mode="RGB")
        added, errors = album.add_photos(self.event, [fake, image_file(), gif])
        self.assertEqual(added, 1)
        self.assertEqual(len(errors), 2)
        self.assertIn("virus.jpg", errors[0])
        self.assertEqual(AlbumPhoto.objects.count(), 1)

    def test_heavy_file_is_refused_before_being_read(self):
        heavy = SimpleUploadedFile("lourde.jpg", b"0" * (album.MAX_FILE_BYTES + 1), content_type="image/jpeg")
        added, errors = album.add_photos(self.event, [heavy])
        self.assertEqual(added, 0)
        self.assertIn("trop lourde", errors[0])

    def test_nothing_chosen_is_an_error(self):
        self.assertEqual(album.add_photos(self.event, [])[0], 0)

    def test_limits_per_upload_per_guest_and_per_event(self):
        with mock.patch.object(album, "MAX_PER_UPLOAD", 2):
            added, errors = album.add_photos(self.event, [image_file(size=(50, 50)) for _ in range(3)])
        self.assertEqual((added, len(errors)), (2, 1))
        with mock.patch.object(album, "MAX_PER_GUEST", 1):
            added, errors = album.add_photos(self.event, [image_file(size=(50, 50)) for _ in range(2)], self.guest)
        self.assertEqual((added, len(errors)), (1, 1))
        self.assertEqual(self.event.photos.filter(guest=self.guest).count(), 1)
        with mock.patch.object(album, "MAX_PER_EVENT", 3):
            added, errors = album.add_photos(self.event, [image_file(size=(50, 50))])
        self.assertEqual(added, 0)
        self.assertIn("complet", errors[0])

    def test_deleting_a_photo_or_the_event_removes_the_files(self):
        album.add_photos(self.event, [image_file(), image_file()])
        first, second = self.event.photos.all()
        paths = [first.image.path, first.thumb.path, second.image.path, second.thumb.path]
        self.assertTrue(all(os.path.exists(p) for p in paths))
        first.delete()
        self.assertFalse(os.path.exists(paths[0]) or os.path.exists(paths[1]))
        self.assertTrue(os.path.exists(paths[2]))
        self.event.delete()
        self.assertFalse(os.path.exists(paths[2]) or os.path.exists(paths[3]))

    def test_zip_holds_every_photo(self):
        album.add_photos(self.event, [image_file(), image_file(), image_file()])
        with zipfile.ZipFile(album.build_zip(self.event)) as archive:
            self.assertEqual(archive.namelist(), ["photo-001.jpg", "photo-002.jpg", "photo-003.jpg"])
            self.assertIsNone(archive.testzip())


@override_settings(MEDIA_ROOT=MEDIA)
class GuestPageTests(TestCase):
    def setUp(self):
        self.event = make_event(thanks_published_at=timezone.now())
        self.guest = make_guest(self.event)
        self.token = self.guest.magic_token

    def url(self, name="invitation_thanks", token=None):
        return reverse(f"events:{name}", args=[token or self.token])

    def test_page_opens_without_login_for_a_guest_who_confirmed(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merci d'avoir été")
        self.assertContains(response, self.event.title)
        self.assertNotIn(reverse("accounts:login"), response.get("Location", ""))

    def test_closed_until_published_and_for_guests_who_did_not_confirm(self):
        Event.objects.filter(pk=self.event.pk).update(thanks_published_at=None)
        self.assertRedirects(self.client.get(self.url()), self.url("invitation"), fetch_redirect_response=False)
        Event.objects.filter(pk=self.event.pk).update(thanks_published_at=timezone.now())
        for status in ("pending", "declined", "maybe"):
            other = make_guest(self.event, f"Autre {status}", status=status, email="")
            self.assertRedirects(self.client.get(self.url(token=other.magic_token)), self.url("invitation", other.magic_token),
                                 fetch_redirect_response=False, msg_prefix=status)
            self.assertEqual(self.client.get(self.url("invitation_album_zip", other.magic_token)).status_code, 302)

    def test_hosts_message_or_default_text(self):
        self.assertContains(self.client.get(self.url()), escape(thanks.default_message()))
        Event.objects.filter(pk=self.event.pk).update(thanks_message="Merci pour cette belle soirée.\nÀ très vite !")
        response = self.client.get(self.url())
        self.assertContains(response, "Merci pour cette belle soirée.<br>À très vite !")
        self.assertNotContains(response, escape(thanks.default_message()))

    def test_personal_thanks_for_gifts_and_for_a_contribution(self):
        self.assertNotContains(self.client.get(self.url()), "thanks-note")
        lamp = Gift.objects.create(event=self.event, name="Lampe", icon_name="bi-lamp")
        GiftClaim.objects.create(gift=lamp, guest=self.guest)
        self.assertContains(self.client.get(self.url()), "Nadège, merci pour votre cadeau : Lampe.")
        vase = Gift.objects.create(event=self.event, name="Vase", icon_name="bi-flower1")
        GiftClaim.objects.create(gift=vase, guest=self.guest)
        self.assertContains(self.client.get(self.url()), "Nadège, merci pour vos cadeaux : Lampe, Vase.")

    def test_personal_thanks_for_a_contribution_never_shows_the_amount(self):
        from payments.models import Contribution, Payment
        payment = Payment.objects.create(kind="contribution", event=self.event, guest=self.guest, method="moncash",
                                         amount_htg=5000, reference="MC-TEST01", status="success")
        Contribution.objects.create(event=self.event, guest=self.guest, payment=payment, amount_htg=5000)
        response = self.client.get(self.url())
        self.assertContains(response, "Nadège, merci pour votre généreuse contribution.")
        self.assertNotContains(response, "5000")

    def test_grid_shows_six_photos_then_the_rest_behind_a_counter(self):
        album.add_photos(self.event, [image_file(size=(60, 60)) for _ in range(6)])
        response = self.client.get(self.url())
        self.assertContains(response, "6 photos")
        self.assertNotContains(response, "album-more")
        album.add_photos(self.event, [image_file(size=(60, 60)) for _ in range(2)])
        response = self.client.get(self.url())
        self.assertContains(response, "8 photos")
        self.assertContains(response, "+2")
        self.assertContains(response, "data-extra", count=2)

    def test_empty_album_has_no_download_button(self):
        response = self.client.get(self.url())
        self.assertContains(response, "L'album est encore vide")
        self.assertNotContains(response, "album.zip")
        self.assertRedirects(self.client.get(self.url("invitation_album_zip")), self.url(), fetch_redirect_response=False)

    def test_guest_adds_photos_and_sees_the_result(self):
        response = self.client.post(self.url(), {"photos": [image_file("a.jpg"), image_file("b.jpg")]})
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)
        self.assertEqual(self.event.photos.filter(guest=self.guest).count(), 2)
        page = self.client.get(self.url())
        self.assertContains(page, "2 photos")
        self.assertContains(page, "2 photos ajoutées. Merci !")

    def test_guest_gets_the_reason_when_a_photo_is_refused(self):
        fake = SimpleUploadedFile("bad.jpg", b"nope", content_type="image/jpeg")
        self.client.post(self.url(), {"photos": [fake]})
        self.assertFalse(AlbumPhoto.objects.exists())
        self.assertContains(self.client.get(self.url()), "n&#x27;est pas une photo valide")

    def test_only_confirmed_guests_can_add_photos(self):
        pending = make_guest(self.event, "En attente", status="pending", email="")
        self.client.post(self.url(token=pending.magic_token), {"photos": [image_file()]})
        self.assertFalse(AlbumPhoto.objects.exists())

    def test_guest_stops_at_the_personal_limit(self):
        with mock.patch.object(album, "MAX_PER_GUEST", 1):
            self.client.post(self.url(), {"photos": [image_file()]})
            response = self.client.get(self.url())
            self.assertContains(response, "Vous avez atteint le nombre de photos")
            self.assertNotContains(response, 'id="photo-input"')

    def test_album_of_another_event_is_never_shown(self):
        other_event = make_event(title="Autre fête", thanks_published_at=timezone.now())
        album.add_photos(other_event, [image_file()])
        album.add_photos(self.event, [image_file(), image_file()])
        response = self.client.get(self.url())
        self.assertContains(response, "2 photos")
        self.assertNotContains(response, "Autre fête")
        self.assertEqual(len(response.context["photos"]), 2)

    def test_zip_download(self):
        album.add_photos(self.event, [image_file(), image_file()])
        response = self.client.get(self.url("invitation_album_zip"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("album-anniversaire-de-mme-duval.zip", response["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(len(archive.namelist()), 2)

    def test_button_on_the_answer_page_only_once_published(self):
        self.assertContains(self.client.get(self.url("invitation")), "Voir les remerciements et l'album")
        Event.objects.filter(pk=self.event.pk).update(thanks_published_at=None)
        self.assertNotContains(self.client.get(self.url("invitation")), "Voir les remerciements")

    def test_the_page_exists_in_each_language(self):
        expected = {"fr": "Merci d'avoir été", "en": "Thank you for", "ht": "Mèsi paske w te"}
        for lang, text in expected.items():
            response = self.client.get(self.url() + f"?lang={lang}")
            self.assertContains(response, text, msg_prefix=lang)
        self.assertContains(self.client.get(self.url() + "?lang=en"), "Add my photos")
        self.assertContains(self.client.get(self.url() + "?lang=ht"), "Ajoute foto mwen yo")
        Gift.objects.create(event=self.event, name="Lampe", icon_name="bi-lamp")
        GiftClaim.objects.create(gift=Gift.objects.get(), guest=self.guest)
        self.assertContains(self.client.get(self.url() + "?lang=en"), "Nadège, thank you for your gift: Lampe.")
        self.assertContains(self.client.get(self.url() + "?lang=ht"), "Nadège, mèsi pou kado w la : Lampe.")


@override_settings(MEDIA_ROOT=MEDIA)
class TeamTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.guest = make_guest(self.event)
        self.admin = make_user("admin@example.com", "admin")
        self.client.login(email="admin@example.com", password=PASSWORD)

    def url(self, name, *args):
        return reverse(f"dashboard:{name}", args=[self.event.pk, *args])

    def test_pages_are_for_the_team_only(self):
        self.client.logout()
        for name in ("thanks_index",):
            self.assertEqual(self.client.get(reverse(f"dashboard:{name}")).status_code, 302)
        self.assertEqual(self.client.get(self.url("thanks_event")).status_code, 302)
        make_user("invite@example.com", "guest")
        self.client.login(email="invite@example.com", password=PASSWORD)
        self.assertIn(self.client.get(self.url("thanks_event")).status_code, (302, 403))
        self.assertIn(self.client.post(self.url("thanks_publish")).status_code, (302, 403))
        self.assertIsNone(Event.objects.get(pk=self.event.pk).thanks_published_at)

    def test_index_and_event_page(self):
        self.assertContains(self.client.get(reverse("dashboard:thanks_index")), self.event.title)
        page = self.client.get(self.url("thanks_event"))
        self.assertContains(page, "Remerciements et album")
        self.assertContains(page, "Nadège Louis")
        self.assertContains(page, "Pas encore publié")
        self.assertContains(self.client.get(reverse("dashboard:event_detail", args=[self.event.pk])), self.url("thanks_event"))

    def test_event_without_present_guests_or_photos_is_not_listed(self):
        quiet = make_event(title="Fête silencieuse")
        make_guest(quiet, "Absent", status="declined")
        self.assertNotContains(self.client.get(reverse("dashboard:thanks_index")), "Fête silencieuse")

    def test_message_is_cleaned_and_limited(self):
        self.client.post(self.url("thanks_message"), {"message": "  Merci   à tous  \r\n\r\n\r\n\r\nÀ bientôt  " + "x" * 700})
        saved = Event.objects.get(pk=self.event.pk).thanks_message
        self.assertTrue(saved.startswith("Merci à tous\n\nÀ bientôt"))
        self.assertEqual(len(saved), thanks.MESSAGE_MAX)

    def test_publish_and_unpublish(self):
        self.client.post(self.url("thanks_publish"))
        first = Event.objects.get(pk=self.event.pk).thanks_published_at
        self.assertIsNotNone(first)
        self.client.post(self.url("thanks_publish"))  # republier ne change pas la date
        self.assertEqual(Event.objects.get(pk=self.event.pk).thanks_published_at, first)
        self.client.post(self.url("thanks_publish"), {"action": "unpublish"})
        self.assertIsNone(Event.objects.get(pk=self.event.pk).thanks_published_at)

    def test_team_adds_and_removes_photos(self):
        self.client.post(self.url("thanks_upload"), {"photos": [image_file(), image_file()]})
        self.assertEqual(self.event.photos.filter(guest__isnull=True).count(), 2)
        photo = self.event.photos.first()
        self.assertContains(self.client.get(self.url("thanks_event")), photo.thumb.url)
        self.client.post(self.url("thanks_photo_delete", photo.pk))
        self.assertEqual(self.event.photos.count(), 1)

    def test_a_photo_of_another_event_cannot_be_deleted_from_this_one(self):
        other = make_event(title="Autre")
        album.add_photos(other, [image_file()])
        response = self.client.post(self.url("thanks_photo_delete", other.photos.get().pk))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other.photos.count(), 1)

    def test_photos_added_by_guests_are_listed_with_their_name(self):
        album.add_photos(self.event, [image_file()], self.guest)
        page = self.client.get(self.url("thanks_event"))
        self.assertContains(page, "1 photo ajoutée")

    def test_form_for_events_does_not_expose_the_thanks_fields(self):
        self.assertNotIn("thanks_published_at", EventForm().fields)


@override_settings(MEDIA_ROOT=MEDIA)
class SendingTests(TestCase):
    def setUp(self):
        self.event = make_event(thanks_published_at=timezone.now())
        self.mailed = make_guest(self.event, "Marie", email="marie@example.com", sent_via="email", language="en")
        self.whatsapp = make_guest(self.event, "Jean", email="", sent_via="whatsapp", phone="+509 3700 1122", language="ht")
        self.admin = make_user("admin@example.com", "admin")
        self.client.login(email="admin@example.com", password=PASSWORD)

    def send_url(self, guest):
        return reverse("dashboard:thanks_send_one", args=[self.event.pk, guest.pk])

    def test_email_goes_out_in_the_guests_language_with_the_personal_link(self):
        response = self.client.post(self.send_url(self.mailed))
        self.assertEqual(response.json(), {"ok": True, "channel": "email", "name": "Marie"})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["marie@example.com"])
        self.assertIn("Thank you for being there", message.subject)
        self.assertIn(f"/invitation/{self.mailed.magic_token}/remerciements/?lang=en", message.body)
        self.assertNotIn("SMS", message.body)
        self.mailed.refresh_from_db()
        self.assertIsNotNone(self.mailed.thanks_sent_at)

    def test_whatsapp_is_only_recorded_and_the_link_is_ready(self):
        response = self.client.post(self.send_url(self.whatsapp))
        self.assertEqual(response.json()["channel"], "whatsapp")
        self.assertEqual(mail.outbox, [])
        self.whatsapp.refresh_from_db()
        self.assertIsNotNone(self.whatsapp.thanks_sent_at)
        page = self.client.get(reverse("dashboard:thanks_event", args=[self.event.pk]))
        self.assertContains(page, "https://wa.me/50937001122?text=")
        self.assertContains(page, f"{self.whatsapp.magic_token}/remerciements/%3Flang%3Dht")

    def test_nothing_is_sent_before_publication(self):
        Event.objects.filter(pk=self.event.pk).update(thanks_published_at=None)
        response = self.client.post(self.send_url(self.mailed))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_only_present_guests_are_thanked(self):
        for status in ("pending", "declined", "maybe"):
            guest = make_guest(self.event, status, status=status)
            self.assertEqual(self.client.post(self.send_url(guest)).status_code, 400, status)
        self.assertEqual(mail.outbox, [])

    def test_a_double_click_does_not_send_twice(self):
        self.assertEqual(self.client.post(self.send_url(self.mailed)).status_code, 200)
        self.assertEqual(self.client.post(self.send_url(self.mailed)).status_code, 400)
        self.assertEqual(len(mail.outbox), 1)
        Guest.objects.filter(pk=self.mailed.pk).update(thanks_sent_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.client.post(self.send_url(self.mailed)).status_code, 200)  # renvoyer est permis plus tard

    def test_guest_without_any_contact_is_refused(self):
        nobody = make_guest(self.event, "Sans contact", email="", phone="")
        self.assertEqual(self.client.post(self.send_url(nobody)).status_code, 400)

    def test_failed_email_is_not_recorded(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("SMTP en panne")):
            response = self.client.post(self.send_url(self.mailed))
        self.assertEqual(response.status_code, 400)
        self.mailed.refresh_from_db()
        self.assertIsNone(self.mailed.thanks_sent_at)

    def test_send_all_sends_emails_and_counts_the_whatsapp_left(self):
        make_guest(self.event, "Déjà remercié", email="deja@example.com", thanks_sent_at=timezone.now())
        response = self.client.post(reverse("dashboard:thanks_send_all", args=[self.event.pk]), follow=True)
        self.assertEqual([m.to for m in mail.outbox], [["marie@example.com"]])
        self.assertContains(response, "1 e-mail de remerciement envoyé.")
        self.assertContains(response, "1 remerciement WhatsApp reste à envoyer")
        self.whatsapp.refresh_from_db()
        self.assertIsNone(self.whatsapp.thanks_sent_at)

    def test_send_all_does_nothing_before_publication(self):
        Event.objects.filter(pk=self.event.pk).update(thanks_published_at=None)
        self.client.post(reverse("dashboard:thanks_send_all", args=[self.event.pk]))
        self.assertEqual(mail.outbox, [])
