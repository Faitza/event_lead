"""Billet d'entrée avec QR code pour les acheteurs et inscription gratuite « Je participe » (20 octobre 2026)."""
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from events.models import Event, Guest
from payments.models import Payment

PAY = {"method": "moncash", "phone": "3712 3456", "otp": "123456"}


def make_user(email, first="Nadège"):
    return CustomUser.objects.create_user(username=email, email=email, password="EventLead2026!", first_name=first,
                                          last_name="Louis", role=CustomUser.Role.GUEST)


def make_event(**kw):
    data = dict(title="Gala test", event_type="public", date=timezone.localdate() + timedelta(days=10),
                time=time(19, 30), venue="Hôtel Montana", max_guests=100)
    data.update(kw)
    return Event.objects.create(**data)


class BoughtTicketTests(TestCase):
    def setUp(self):
        self.user = make_user("nadege@test.ht")
        self.client.force_login(self.user)
        self.event = make_event(price_htg=3500)

    def buy(self, quantity=2, key="a" * 32, **extra):
        return self.client.post(reverse("payments:checkout", args=[self.event.pk]),
                                {**PAY, "quantity": quantity, "idem": key, **extra}, follow=True)

    def test_paid_ticket_gives_a_qr_ticket_for_all_places(self):
        response = self.buy(2)
        payment = Payment.objects.get(kind=Payment.Kind.TICKET)
        guest = Guest.objects.get(event=self.event, user=self.user)
        self.assertEqual(payment.guest, guest)
        self.assertTrue(guest.from_ticket)
        self.assertEqual(guest.status, Guest.Status.CONFIRMED)
        self.assertEqual(guest.party_size, 2)
        self.assertContains(response, "Votre billet est prêt")
        self.assertContains(response, guest.get_ticket_url())
        ticket = self.client.get(guest.get_ticket_url())
        self.assertContains(ticket, "Votre billet pour")
        self.assertContains(ticket, payment.reference)
        self.assertContains(ticket, "2 places")
        self.assertContains(ticket, guest.entry_code)
        self.assertContains(ticket, reverse("accounts:guest_space"))

    def test_second_purchase_adds_places_to_the_same_ticket(self):
        self.buy(2, key="a" * 32)
        self.buy(1, key="b" * 32)
        guest = Guest.objects.get(event=self.event, user=self.user)
        self.assertEqual(guest.party_size, 3)

    def test_failed_payment_gives_no_ticket(self):
        response = self.buy(1, otp="000000")
        self.assertFalse(Guest.objects.filter(event=self.event, user=self.user).exists())
        self.assertNotContains(response, "Votre billet est prêt")

    def test_invited_person_who_buys_keeps_one_ticket(self):
        invited = Guest.objects.create(event=self.event, user=self.user, name="Nadège Louis", email=self.user.email)
        self.buy(2)
        self.assertEqual(Guest.objects.filter(event=self.event, user=self.user).count(), 1)
        invited.refresh_from_db()
        self.assertEqual(invited.status, Guest.Status.CONFIRMED)
        self.assertEqual(invited.party_size, 2)
        self.assertFalse(invited.from_ticket)

    def test_my_space_lists_my_tickets(self):
        self.buy(2)
        guest = Guest.objects.get(event=self.event, user=self.user)
        response = self.client.get(reverse("accounts:guest_space"))
        self.assertContains(response, "Mes billets")
        self.assertContains(response, Payment.objects.get().reference)
        self.assertContains(response, guest.get_ticket_url())
        self.assertContains(response, "Aucune invitation liée")  # pas en double dans Mes invitations

    def test_success_page_of_other_kinds_has_no_ticket_box(self):
        self.client.post(reverse("payments:vip"), {**PAY, "idem": "c" * 32})
        payment = Payment.objects.get(kind=Payment.Kind.ORGANIZER_ACCESS)
        response = self.client.get(reverse("payments:success", args=[payment.reference]))
        self.assertNotContains(response, "Voir mon billet")


class FreeRegistrationTests(TestCase):
    def setUp(self):
        self.user = make_user("nadege@test.ht")
        self.event = make_event()

    def test_visitor_is_sent_to_login(self):
        response = self.client.get(reverse("events:public_detail", args=[self.event.pk]))
        self.assertContains(response, "Je participe")
        self.assertContains(response, reverse("accounts:login"))
        self.assertEqual(self.client.post(reverse("events:participate", args=[self.event.pk])).status_code, 302)
        self.assertFalse(Guest.objects.exists())

    def test_participate_gives_a_free_ticket(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("events:participate", args=[self.event.pk]), follow=True)
        guest = Guest.objects.get(event=self.event, user=self.user)
        self.assertTrue(guest.from_ticket)
        self.assertEqual(guest.status, Guest.Status.CONFIRMED)
        self.assertContains(response, "Entrée gratuite")
        self.assertContains(response, guest.entry_code)
        self.client.post(reverse("events:participate", args=[self.event.pk]))  # deuxième clic : rien de plus
        self.assertEqual(Guest.objects.count(), 1)
        space = self.client.get(reverse("accounts:guest_space"))
        self.assertContains(space, "Mes billets")
        self.assertContains(space, "Gratuit")
        detail = self.client.get(reverse("events:public_detail", args=[self.event.pk]))
        self.assertContains(detail, "Voir mon billet")

    def test_full_event(self):
        self.event.max_guests = 1
        self.event.save()
        Guest.objects.create(event=self.event, name="Quelqu'un")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("events:public_detail", args=[self.event.pk])), "Complet")
        response = self.client.post(reverse("events:participate", args=[self.event.pk]), follow=True)
        self.assertContains(response, "plus de place")
        self.assertFalse(Guest.objects.filter(user=self.user).exists())

    def test_not_for_paid_private_or_past_events(self):
        self.client.force_login(self.user)
        for event in (make_event(price_htg=1500), make_event(event_type="private"),
                      make_event(date=timezone.localdate() - timedelta(days=1))):
            self.assertEqual(self.client.post(reverse("events:participate", args=[event.pk])).status_code, 404)
        self.assertFalse(Guest.objects.exists())
