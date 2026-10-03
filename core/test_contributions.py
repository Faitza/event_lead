"""Tests de la contribution en argent : montant, MonCash / NatCash, réponse confirmée en une étape, confidentialité, équipe."""
import re
from datetime import time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from events.forms import EventForm
from events.models import Event, Guest
from gifts.models import Gift, GiftClaim
from gifts.services import ResponseLockedError, confirm_response
from payments import contributions
from payments.contributions import ContributionError, parse_amount
from payments.models import Contribution, Payment

PASSWORD = "MotDePasse-Solide-42"


def make_event(**kw):
    defaults = dict(title="Mariage de Sarah et Jean-Marc", event_type="private", date=timezone.localdate() + timedelta(days=30),
                    time=time(16, 0), venue="Pétion-Ville", max_guests=100, allow_companions=True, max_companions=2,
                    accept_contributions=True)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def make_guest(event, name="Carla", **kw):
    return Guest.objects.create(event=event, name=name, phone="+509 3712 3456", **kw)


def make_user(email, role="guest"):
    return CustomUser.objects.create_user(username=email, email=email, password=PASSWORD, role=role)


def pay_data(method="moncash", amount=5000, message="", **extra):
    data = {"method": method, "amount": amount, "message": message, "phone": "3712 3456"}
    data.update({"moncash": {"otp": "123456"}, "natcash": {"pin": "1234"}}.get(method, {}))
    data.update(extra)
    return data


class ParseAmountTests(TestCase):
    def test_accepts_spaces_dots_and_commas(self):
        for raw in ("5000", "5 000", "5.000", "5,000", " 5000 ", "5 000", 5000):
            self.assertEqual(parse_amount(raw), Decimal(5000), raw)

    def test_refuses_what_is_not_an_amount(self):
        for raw in ("", None, "abc", "12 abc", "-500", "1.5e3"):
            with self.assertRaises(ContributionError, msg=raw):
                parse_amount(raw)

    def test_minimum_and_maximum(self):
        self.assertEqual(parse_amount(contributions.MIN_AMOUNT), Decimal(contributions.MIN_AMOUNT))
        self.assertEqual(parse_amount(contributions.MAX_AMOUNT), Decimal(contributions.MAX_AMOUNT))
        with self.assertRaises(ContributionError):
            parse_amount(contributions.MIN_AMOUNT - 1)
        with self.assertRaises(ContributionError):
            parse_amount(contributions.MAX_AMOUNT + 1)

    def test_usd_equivalent_uses_the_fixed_rate(self):
        self.assertEqual(contributions.usd(5000), Decimal("37.50"))

    def test_message_is_trimmed_and_limited(self):
        self.assertEqual(contributions.clean_message("  Bravo\n\n  à vous  "), "Bravo à vous")
        self.assertEqual(len(contributions.clean_message("x" * 1000)), Contribution.MESSAGE_MAX)


class ContributionFlowTests(TestCase):
    """Événement avec une liste de cadeaux ET les contributions en argent."""

    def setUp(self):
        self.event = make_event()
        self.gift = Gift.objects.create(event=self.event, name="Lampe", icon_name="bi-lamp")
        self.guest = make_guest(self.event)
        self.token = self.guest.magic_token

    def url(self, name):
        return reverse(f"events:{name}", args=[self.token])

    def confirm_presence(self, companions=1):
        return self.client.post(self.url("invitation"), {"status": "confirmed", "companions": companions})

    def test_guest_is_never_asked_to_log_in(self):
        self.confirm_presence()
        response = self.client.get(self.url("invitation_contribution"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(reverse("accounts:login"), response.get("Location", ""))

    def test_page_shows_amounts_methods_and_privacy_note(self):
        self.confirm_presence()
        response = self.client.get(self.url("invitation_contribution"))
        for text in ("Contribuer en", "Autre montant", "MonCash", "NatCash", "Seuls les hôtes voient votre nom et votre montant",
                     "Je préfère choisir un cadeau"):
            self.assertContains(response, text)
        for value in contributions.PRESET_AMOUNTS:
            self.assertContains(response, f'data-amount="{value}"')
        self.assertNotContains(response, 'data-method="stripe"')
        self.assertNotContains(response, 'data-method="paypal"')
        self.assertContains(response, 'data-rate="0.0075"')  # 5 000 HTG = 37,50 USD

    def test_page_needs_a_confirmed_presence_in_the_session(self):
        self.assertRedirects(self.client.get(self.url("invitation_contribution")), self.url("invitation"))
        self.client.post(self.url("invitation"), {"status": "declined"})
        self.assertRedirects(self.client.get(self.url("invitation_contribution")), self.url("invitation"))

    def test_page_is_closed_when_the_event_does_not_accept_contributions(self):
        self.confirm_presence()
        Event.objects.filter(pk=self.event.pk).update(accept_contributions=False)
        self.assertRedirects(self.client.get(self.url("invitation_contribution")), self.url("invitation"))
        response = self.client.post(self.url("invitation_contribution"), pay_data())
        self.assertRedirects(response, self.url("invitation"))
        self.assertFalse(Payment.objects.exists())

    def test_link_to_contribute_only_appears_when_the_event_accepts_it(self):
        self.confirm_presence()
        link = reverse("events:invitation_contribution", args=[self.token])
        self.assertContains(self.client.get(self.url("invitation_gift_question")), link)
        Event.objects.filter(pk=self.event.pk).update(accept_contributions=False)
        self.assertNotContains(self.client.get(self.url("invitation_gift_question")), link)

    def test_moncash_contribution_confirms_the_answer_in_one_step(self):
        self.confirm_presence(companions=1)
        response = self.client.post(self.url("invitation_contribution"), pay_data("moncash", 7500, "Tous nos vœux  !"))
        self.assertRedirects(response, self.url("invitation_done"), fetch_redirect_response=False)
        self.guest.refresh_from_db()
        self.assertEqual((self.guest.status, self.guest.companions, self.guest.wants_gift), ("confirmed", 1, False))
        self.assertTrue(self.guest.is_locked)
        contribution = Contribution.objects.get()
        self.assertEqual((contribution.guest, contribution.event, contribution.amount_htg), (self.guest, self.event, Decimal(7500)))
        self.assertEqual(contribution.message, "Tous nos vœux !")
        self.assertEqual(contribution.amount_usd, Decimal("56.25"))
        payment = contribution.payment
        self.assertEqual((payment.kind, payment.status, payment.method), ("contribution", "success", "moncash"))
        self.assertEqual(payment.amount_htg, Decimal(7500))
        self.assertIsNone(payment.user)
        self.assertEqual(payment.guest, self.guest)
        self.assertFalse(GiftClaim.objects.exists())

    def test_natcash_contribution(self):
        self.confirm_presence()
        response = self.client.post(self.url("invitation_contribution"), pay_data("natcash", 25000))
        self.assertRedirects(response, self.url("invitation_done"), fetch_redirect_response=False)
        contribution = Contribution.objects.get()
        self.assertEqual((contribution.payment.method, contribution.amount_htg), ("natcash", Decimal(25000)))

    def test_thank_you_page_and_later_visits_show_the_contribution(self):
        self.confirm_presence()
        self.client.post(self.url("invitation_contribution"), pay_data("moncash", 10000))
        done = self.client.get(self.url("invitation_done"))
        self.assertContains(done, "Votre contribution")
        self.assertContains(done, "MonCash")
        self.assertTrue(re.search(r"10\W000 HTG", done.content.decode()))
        later = self.client.get(self.url("invitation"))
        self.assertContains(later, "Cette réponse est définitive")
        self.assertContains(later, "Votre contribution")

    def test_wrong_otp_is_refused_and_the_answer_stays_open(self):
        self.confirm_presence()
        response = self.client.post(self.url("invitation_contribution"), pay_data("moncash", 2500, "Bravo", otp="000000"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Code OTP MonCash incorrect")
        self.assertContains(response, 'data-reopen="moncash"')  # la fenêtre de paiement se rouvre avec le motif
        self.assertContains(response, "Bravo")  # le petit mot est gardé
        self.assertFalse(Contribution.objects.exists())
        self.assertEqual(Payment.objects.get().status, "failed")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.status, Guest.Status.PENDING)
        self.assertFalse(self.guest.is_locked)
        # Un deuxième essai avec le bon code réussit
        response = self.client.post(self.url("invitation_contribution"), pay_data("moncash", 2500, "Bravo"))
        self.assertRedirects(response, self.url("invitation_done"), fetch_redirect_response=False)
        self.assertEqual(Payment.objects.filter(status="success").count(), 1)
        self.assertEqual(Contribution.objects.count(), 1)

    def test_only_moncash_and_natcash_are_accepted(self):
        self.confirm_presence()
        card = pay_data("stripe", 5000, card_number="4242 4242 4242 4242", card_expiry="12/40", card_cvc="123", card_name="A B")
        paypal = pay_data("paypal", 5000, paypal_email="a@example.com", paypal_password="x")
        for data in (card, paypal):
            response = self.client.post(self.url("invitation_contribution"), data)
            self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Contribution.objects.exists())

    def test_service_refuses_other_methods_directly(self):
        with self.assertRaises(ContributionError):
            contributions.contribute(self.guest, companions=0, amount=Decimal(5000), method="stripe", cleaned={}, message="")
        self.assertFalse(Payment.objects.exists())

    def test_invalid_amounts_are_refused_before_any_payment(self):
        self.confirm_presence()
        for raw in ("", "abc", "100", "900000"):
            response = self.client.post(self.url("invitation_contribution"), pay_data("moncash", raw))
            self.assertEqual(response.status_code, 200, raw)
        self.assertFalse(Payment.objects.exists())
        self.guest.refresh_from_db()
        self.assertFalse(self.guest.is_locked)

    def test_phone_and_codes_are_validated(self):
        self.confirm_presence()
        response = self.client.post(self.url("invitation_contribution"), pay_data("moncash", 5000, phone="12"))
        self.assertContains(response, "Numéro haïtien invalide")
        response = self.client.post(self.url("invitation_contribution"), pay_data("natcash", 5000, pin="12"))
        self.assertContains(response, "Le code PIN contient 4 chiffres")
        self.assertFalse(Payment.objects.exists())

    def test_no_second_charge_once_the_answer_is_final(self):
        self.confirm_presence()
        self.client.post(self.url("invitation_contribution"), pay_data("moncash", 5000))
        response = self.client.post(self.url("invitation_contribution"), pay_data("moncash", 9000))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cette réponse est définitive")
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Contribution.objects.get().amount_htg, Decimal(5000))

    def test_service_refuses_a_guest_who_already_answered(self):
        confirm_response(self.guest.pk, "confirmed", 0, False, [])
        with self.assertRaises(ResponseLockedError):
            contributions.contribute(self.guest, companions=0, amount=Decimal(5000), method="moncash",
                                     cleaned={"otp": "123456", "payer_detail": ""}, message="")
        self.assertFalse(Payment.objects.exists())

    def test_choosing_a_gift_instead(self):
        self.confirm_presence()
        response = self.client.post(self.url("invitation_gift_question"), {"wants_gift": "yes"})
        self.assertRedirects(response, self.url("invitation_gift_list"))

    def test_one_guest_cannot_contribute_twice(self):
        self.confirm_presence()
        self.client.post(self.url("invitation_contribution"), pay_data("moncash", 5000))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Contribution.objects.create(event=self.event, guest=self.guest, payment=Payment.objects.get(), amount_htg=1)


class MoneyOnlyEventTests(TestCase):
    """Événement sans liste de cadeaux : seule la contribution en argent est proposée."""

    def setUp(self):
        self.event = make_event()
        self.guest = make_guest(self.event)
        self.token = self.guest.magic_token

    def url(self, name):
        return reverse(f"events:{name}", args=[self.token])

    def test_presence_leads_to_the_contribution_question(self):
        response = self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 0})
        self.assertRedirects(response, self.url("invitation_gift_question"))
        page = self.client.get(self.url("invitation_gift_question"))
        self.assertContains(page, "Contribuer en argent")
        self.assertContains(page, "Non merci, continuer")
        self.assertEqual(page.context["step_total"], 4)

    def test_declining_the_contribution_goes_to_the_recap(self):
        self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 0})
        response = self.client.post(self.url("invitation_gift_question"), {"wants_gift": "no"})
        self.assertRedirects(response, self.url("invitation_recap"))
        self.client.post(self.url("invitation_recap"))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.status, "confirmed")
        self.assertFalse(Contribution.objects.exists())

    def test_wanting_a_gift_is_ignored_when_there_is_no_gift_list(self):
        self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 0})
        response = self.client.post(self.url("invitation_gift_question"), {"wants_gift": "yes"})
        self.assertRedirects(response, self.url("invitation_recap"))

    def test_contribution_page_has_no_gift_link_and_works(self):
        self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 2})
        page = self.client.get(self.url("invitation_contribution"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Je préfère choisir un cadeau")
        response = self.client.post(self.url("invitation_contribution"), pay_data("natcash", 1000))
        self.assertRedirects(response, self.url("invitation_done"), fetch_redirect_response=False)
        self.guest.refresh_from_db()
        self.assertEqual((self.guest.status, self.guest.companions), ("confirmed", 2))
        self.assertIsNone(self.guest.wants_gift)  # pas de liste de cadeaux : la question ne se pose pas

    def test_declining_the_invitation_never_asks_for_money(self):
        response = self.client.post(self.url("invitation"), {"status": "declined"})
        self.assertRedirects(response, self.url("invitation_recap"))

    def test_event_without_contributions_and_gifts_is_unchanged(self):
        Event.objects.filter(pk=self.event.pk).update(accept_contributions=False)
        response = self.client.post(self.url("invitation"), {"status": "confirmed", "companions": 0})
        self.assertRedirects(response, self.url("invitation_recap"))
        self.assertFalse(Event.objects.get(pk=self.event.pk).has_gift_step)


class PrivacyAndTeamTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.donor = make_guest(self.event, "Fabiola Désir", email="fabiola@example.com")
        self.other = make_guest(self.event, "Roseline Augustin")
        self.client.post(reverse("events:invitation", args=[self.donor.magic_token]), {"status": "confirmed", "companions": 0})
        self.client.post(reverse("events:invitation_contribution", args=[self.donor.magic_token]),
                         pay_data("moncash", 12345, "Message secret pour les mariés"))
        self.contribution = Contribution.objects.get()
        self.admin = make_user("admin@example.com", "admin")

    def test_other_guests_never_see_amounts_names_or_messages(self):
        self.client.logout()
        other_client = self.client_class()
        for name in ("invitation", "invitation_gift_question", "invitation_contribution", "invitation_recap"):
            response = other_client.get(reverse(f"events:{name}", args=[self.other.magic_token]))
            html = response.content.decode()
            self.assertNotIn("Fabiola", html, name)
            self.assertNotIn("secret", html, name)
            self.assertFalse(re.search(r"12\W345", html), name)

    def test_team_sees_the_contribution_in_the_event_follow_up(self):
        self.client.login(email="admin@example.com", password=PASSWORD)
        for name in ("event_detail", "event_live"):
            response = self.client.get(reverse(f"dashboard:{name}", args=[self.event.pk]))
            html = response.content.decode()
            self.assertContains(response, "Contributions en argent", msg_prefix=name)
            self.assertContains(response, "Fabiola Désir", msg_prefix=name)
            self.assertContains(response, "Message secret pour les mariés", msg_prefix=name)
            self.assertTrue(re.search(r"12\W345 HTG", html), name)
            self.assertEqual(response.context["contributions_total"], Decimal(12345))

    def test_follow_up_without_contribution_shows_the_empty_state(self):
        other_event = make_event(title="Autre fête")
        self.client.login(email="admin@example.com", password=PASSWORD)
        response = self.client.get(reverse("dashboard:event_detail", args=[other_event.pk]))
        self.assertContains(response, "Aucune contribution pour l'instant.")

    def test_dashboard_stays_closed_to_non_admins(self):
        url = reverse("dashboard:event_live", args=[self.event.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # pas connecté
        make_user("invite@example.com", "guest")
        self.client.login(email="invite@example.com", password=PASSWORD)
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403))
        self.assertNotIn(b"Message secret", response.content)

    def test_guest_with_a_contribution_cannot_be_deleted(self):
        self.client.login(email="admin@example.com", password=PASSWORD)
        url = reverse("dashboard:guest_delete", args=[self.donor.pk])
        self.assertContains(self.client.get(url), "choix de cadeaux ou à des contributions")
        self.client.post(url)
        self.assertTrue(Guest.objects.filter(pk=self.donor.pk).exists())
        self.assertEqual(Contribution.objects.count(), 1)

    def test_event_with_a_contribution_cannot_be_deleted(self):
        self.client.login(email="admin@example.com", password=PASSWORD)
        self.client.post(reverse("dashboard:event_delete", args=[self.event.pk]))
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_guest_without_contribution_can_still_be_deleted(self):
        self.client.login(email="admin@example.com", password=PASSWORD)
        self.client.post(reverse("dashboard:guest_delete", args=[self.other.pk]))
        self.assertFalse(Guest.objects.filter(pk=self.other.pk).exists())

    def test_event_form_has_the_toggle(self):
        self.assertIn("accept_contributions", EventForm().fields)
        self.client.login(email="admin@example.com", password=PASSWORD)
        response = self.client.get(reverse("dashboard:event_edit", args=[self.event.pk]))
        self.assertContains(response, 'name="accept_contributions"')
        self.assertFalse(Event._meta.get_field("accept_contributions").default)


class ContributionLanguagesTests(TestCase):
    """Le parcours de contribution existe en français, anglais et créole (le créole est un brouillon à relire)."""

    def setUp(self):
        self.event = make_event()
        self.guest = make_guest(self.event)
        self.token = self.guest.magic_token
        self.client.post(reverse("events:invitation", args=[self.token]), {"status": "confirmed", "companions": 0})

    def get(self, name, lang):
        return self.client.get(reverse(f"events:{name}", args=[self.token]) + f"?lang={lang}")

    def test_question_and_page_in_each_language(self):
        expected = {
            "fr": ("Contribuer en argent", "Un petit mot pour les hôtes"),
            "en": ("Contribute money", "A short note for the hosts"),
            "ht": ("Kontribye ak lajan", "Yon ti mo pou òganizatè yo"),
        }
        for lang, (button, note) in expected.items():
            self.assertContains(self.get("invitation_gift_question", lang), button, msg_prefix=lang)
            self.assertContains(self.get("invitation_contribution", lang), note, msg_prefix=lang)

    def test_amount_messages_and_privacy_note_are_translated(self):
        page = self.get("invitation_contribution", "en")
        self.assertContains(page, "The minimum amount is 500 HTG.")
        self.assertContains(page, "Only the hosts see your name and amount.")
        page = self.get("invitation_contribution", "ht")
        self.assertContains(page, "Montan minimòm lan se 500 HTG.")
        self.assertContains(page, "Se sèlman òganizatè yo ki wè non w ak montan w.")

    def test_refused_payment_message_is_translated(self):
        data = pay_data("moncash", 5000, otp="000000")
        response = self.client.post(reverse("events:invitation_contribution", args=[self.token]) + "?lang=en", data)
        self.assertContains(response, "Incorrect MonCash OTP code")


class MoneyFormatTests(TestCase):
    """Séparateurs de milliers : espace en français et en créole, virgule en anglais (comme les scripts de la page)."""

    def test_htg_and_usd_filters_follow_the_language(self):
        from django.utils import translation

        from core.templatetags.el_tags import htg, usd

        for lang, expected_htg, expected_usd in (
            ("fr", "25 000", "187,50"), ("ht", "25 000", "187,50"), ("en", "25,000", "187.50"),
        ):
            with translation.override(lang):
                self.assertEqual(htg(Decimal("25000.00")), expected_htg, lang)
                self.assertEqual(usd(Decimal("187.5")), expected_usd, lang)
        with translation.override("fr"):
            self.assertEqual(htg(500), "500")
            self.assertEqual(htg(1234567), "1 234 567")
