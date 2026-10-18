"""Plusieurs personnes en même temps : les écritures prennent leur tour, les limites tiennent."""
import threading
import uuid
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import CustomUser
from events.models import Event, Guest
from payments import tickets
from payments.models import Payment

from .tests import PASSWORD, make_event, make_user


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


def buy_data(quantity=1):
    return {"method": "moncash", "phone": "3712 3456", "otp": "123456", "idem": uuid.uuid4().hex, "quantity": quantity}


class TicketLimitTests(TestCase):
    def setUp(self):
        self.event = make_event(event_type="public", price_htg=1500, max_guests=3)
        self.client.force_login(make_user("acheteur@x.ht"))
        self.url = reverse("payments:checkout", args=[self.event.pk])

    def test_sales_stop_when_the_event_is_full(self):
        self.assertEqual(self.client.post(self.url, buy_data(3)).status_code, 302)
        self.assertEqual(tickets.tickets_left(self.event), 0)
        r = self.client.post(self.url, buy_data(1))
        self.assertContains(r, "complet")
        self.assertEqual(Payment.objects.filter(kind=Payment.Kind.TICKET).count(), 1)
        self.assertContains(self.client.get(self.url), "plus de billets en vente")
        self.assertContains(self.client.get(self.event.get_absolute_url()), "Complet")
        self.assertContains(self.client.get(reverse("payments:ticketing")), "Complet")

    def test_asking_more_than_what_is_left_is_refused_without_charge(self):
        self.client.post(self.url, buy_data(2))
        r = self.client.post(self.url, buy_data(2))
        self.assertContains(r, "Il ne reste que 1 billet")
        self.assertEqual(Payment.objects.filter(kind=Payment.Kind.TICKET).count(), 1)
        self.assertContains(self.client.get(self.url), 'max="1"')

    def test_failed_and_abandoned_payments_give_the_seats_back(self):
        Payment.objects.create(kind=Payment.Kind.TICKET, event=self.event, quantity=2, amount_htg=3000,
                               method="moncash", status=Payment.Status.FAILED, reference="F1")
        old = Payment.objects.create(kind=Payment.Kind.TICKET, event=self.event, quantity=1, amount_htg=1500,
                                     method="moncash", status=Payment.Status.PENDING, reference="P1")
        self.assertEqual(tickets.tickets_left(self.event), 2)
        Payment.objects.filter(pk=old.pk).update(created_at=old.created_at - tickets.PENDING_HOLD - timedelta(minutes=1))
        self.assertEqual(tickets.tickets_left(self.event), 3)

    def test_same_form_sent_twice_on_the_last_ticket_is_not_called_full(self):
        data = buy_data(3)
        self.client.post(self.url, data)
        r = self.client.post(self.url, data, follow=True)
        self.assertContains(r, "déjà été effectué")


class RealConcurrencyTests(TransactionTestCase):
    """Vrais achats au même instant (plusieurs connexions) : seulement sur PostgreSQL, comme en ligne."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("test de concurrence réelle : PostgreSQL uniquement")
        self.event = make_event(event_type="public", price_htg=1500, max_guests=1)

    def test_two_buyers_of_the_last_ticket_only_one_gets_it(self):
        barrier, results = threading.Barrier(5), []

        def buy(i):
            from django.db import connections
            try:
                barrier.wait()
                tickets.reserve(uuid.uuid4().hex, self.event, 1, amount_htg=1500, method="moncash", reference=f"R{i}")
                results.append("ok")
            except tickets.SoldOutError:
                results.append("complet")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=buy, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ["complet"] * 4 + ["ok"])
        self.assertEqual(Payment.objects.filter(kind=Payment.Kind.TICKET).count(), 1)
