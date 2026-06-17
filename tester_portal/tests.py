from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.models import Ticket, TicketEvent

User = get_user_model()
S  = Ticket.Status
SS = Ticket.SubStatus


class TesterPortalTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")

        self.dev = User.objects.create_user(
            "dev1", email="dev1@test.local", password="pw", role="developer"
        )
        self.tester = User.objects.create_user(
            "tester1", email="tester1@test.local", password="pw", role="tester"
        )
        self.tester2 = User.objects.create_user(
            "tester2", email="tester2@test.local", password="pw", role="tester"
        )
        self.client_user = User.objects.create_user(
            "cli1", email="cli1@test.local", password="pw", role="client",
            client=self.org,
        )

        self.client.force_login(self.tester)

    def _make_ticket(self, sub_status=SS.TESTING, tester=None, status=S.IN_PROGRESS):
        return Ticket.objects.create(
            subject="Test ticket",
            description="A test description.",
            requester=self.client_user,
            client=self.org,
            status=status,
            sub_status=sub_status if status == S.IN_PROGRESS else None,
            assigned_developer=self.dev,
            assigned_tester=tester if tester is not None else self.tester,
        )

    # ── Dashboard ────────────────────────────────────────────────────────────

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("tester:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_dashboard_requires_tester_role(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("tester:dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_shows_only_assigned_tickets(self):
        own   = self._make_ticket()
        other = self._make_ticket(tester=self.tester2)
        resp  = self.client.get(reverse("tester:dashboard"))
        self.assertEqual(resp.status_code, 200)
        ids = [t.pk for t in resp.context["assigned_tickets"]]
        self.assertIn(own.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_dashboard_context_counts(self):
        self._make_ticket(sub_status=SS.TESTING)
        self._make_ticket(sub_status=SS.TESTING)
        self._make_ticket(sub_status=SS.READY_FOR_UAT)
        self._make_ticket(sub_status=SS.RETURNED)
        resp = self.client.get(reverse("tester:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["testing_count"], 2)
        self.assertEqual(resp.context["passed_count"], 1)
        self.assertEqual(resp.context["failed_count"], 1)

    # ── Detail ───────────────────────────────────────────────────────────────

    def test_detail_requires_login(self):
        ticket = self._make_ticket()
        self.client.logout()
        resp = self.client.get(reverse("tester:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_detail_requires_tester_role(self):
        ticket = self._make_ticket()
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("tester:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_detail_own_testing_ticket_ok(self):
        ticket = self._make_ticket()
        resp = self.client.get(reverse("tester:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["ticket"].pk, ticket.pk)

    def test_detail_other_testers_ticket_is_404(self):
        other_ticket = self._make_ticket(tester=self.tester2)
        resp = self.client.get(reverse("tester:ticket_detail", args=[other_ticket.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_detail_ticket_past_visible_range_is_404(self):
        # Realistic post-lifecycle state: send_to_uat sets status=UAT, sub_status=None.
        # assigned_tester is still set on the row but the tester has no visibility per TARGET §6.
        ticket = self._make_ticket(status=S.UAT)
        resp = self.client.get(reverse("tester:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 404)

    # ── Transitions ──────────────────────────────────────────────────────────

    def test_transition_pass_moves_to_ready_for_uat(self):
        ticket = self._make_ticket(sub_status=SS.TESTING)
        resp = self.client.post(
            reverse("tester:ticket_transition", args=[ticket.pk]),
            {"action": "pass"},
        )
        self.assertRedirects(resp, reverse("tester:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.READY_FOR_UAT)

    def test_transition_fail_with_notes_moves_to_returned(self):
        ticket = self._make_ticket(sub_status=SS.TESTING)
        resp = self.client.post(
            reverse("tester:ticket_transition", args=[ticket.pk]),
            {"action": "fail", "failure_notes": "Login button unresponsive on mobile."},
        )
        self.assertRedirects(resp, reverse("tester:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.RETURNED)
        # Verify failure notes stored in the TicketEvent
        event = TicketEvent.objects.filter(ticket=ticket, action="fail").first()
        self.assertIsNotNone(event)
        self.assertIn("Login button", event.note)

    def test_transition_fail_without_notes_is_error(self):
        ticket = self._make_ticket(sub_status=SS.TESTING)
        # follow=True so the final response has messages in context (assertRedirects consumes them)
        resp = self.client.post(
            reverse("tester:ticket_transition", args=[ticket.pk]),
            {"action": "fail", "failure_notes": ""},
            follow=True,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.TESTING)
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("failure_notes" in m or "fail" in m.lower() for m in msgs))

    def test_transition_unassigned_ticket_is_404(self):
        other_ticket = self._make_ticket(tester=self.tester2)
        resp = self.client.post(
            reverse("tester:ticket_transition", args=[other_ticket.pk]),
            {"action": "pass"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_transition_disallowed_action_blocked(self):
        ticket = self._make_ticket(sub_status=SS.TESTING)
        resp = self.client.post(
            reverse("tester:ticket_transition", args=[ticket.pk]),
            {"action": "approve"},
        )
        # Rejected at whitelist — redirects to detail, ticket unchanged
        self.assertRedirects(resp, reverse("tester:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.TESTING)

    # ── Form markup integrity ─────────────────────────────────────────────────

    def test_form_markup_pass(self):
        ticket = self._make_ticket(sub_status=SS.TESTING)
        resp = self.client.get(reverse("tester:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        transition_url = reverse("tester:ticket_transition", args=[ticket.pk])
        self.assertIn(f'action="{transition_url}"', html)
        self.assertIn('name="action" value="pass"', html)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_form_markup_fail(self):
        ticket = self._make_ticket(sub_status=SS.TESTING)
        resp = self.client.get(reverse("tester:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        transition_url = reverse("tester:ticket_transition", args=[ticket.pk])
        self.assertIn(f'action="{transition_url}"', html)
        self.assertIn('name="action" value="fail"', html)
        self.assertIn('name="failure_notes"', html)
        self.assertIn("csrfmiddlewaretoken", html)
