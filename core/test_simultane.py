"""Plusieurs personnes en même temps : les écritures prennent leur tour, les limites tiennent."""
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from events.models import Event, Guest

from .tests import PASSWORD, make_event


class SimultaneousUseTests(TestCase):
    def setUp(self):
        self.event = make_event(max_guests=2)
        CustomUser.objects.create_user(username="ad@x.ht", email="ad@x.ht", password=PASSWORD, role="admin")
        self.client.login(email="ad@x.ht", password=PASSWORD)

    def add(self, name):
        return self.client.post(reverse("dashboard:guest_create"), {
            "event": self.event.pk, "name": name, "email": f"{name.lower()}@x.ht", "phone": "",
            "sent_via": "email", "language": "fr",
        })

    def test_sqlite_writes_take_their_turn_from_the_start(self):
        db = settings.DATABASES["default"]
        if db["ENGINE"] != "django.db.backends.sqlite3":
            self.skipTest("réglage propre à SQLite")
        self.assertEqual(db["OPTIONS"]["transaction_mode"], "IMMEDIATE")

    def test_adding_a_guest_locks_the_event_before_counting(self):
        with mock.patch.object(Event.objects, "select_for_update", wraps=Event.objects.select_for_update) as lock:
            r = self.add("Marc")
        self.assertEqual(r.status_code, 302)
        lock.assert_called_once()
        self.assertTrue(Guest.objects.filter(name="Marc").exists())

    def test_the_guest_limit_still_holds(self):
        self.assertEqual(self.add("Anne").status_code, 302)
        self.assertEqual(self.add("Paul").status_code, 302)
        r = self.add("Rose")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "nombre maximum")
        self.assertEqual(self.event.guests.count(), 2)
