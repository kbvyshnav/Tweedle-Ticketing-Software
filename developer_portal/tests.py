from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.models import Ticket

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class DeveloperPortalTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")

        self.dev = User.objects.create_user(
            "dev1", email="dev1@test.local", password="pw", role="developer"
        )
        self.dev2 = User.objects.create_user(
            "dev2", email="dev2@test.local", password="pw", role="developer"
        )
        self.client_user = User.objects.create_user(
            "cli1", email="cli1@test.local", password="pw", role="client",
            client=self.org,
        )

        self.client.force_login(self.dev)

    def _make_ticket(self, status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT,
                     developer=None, tester=None):
        return Ticket.objects.create(
            subject="Test ticket",
            description="A test description.",
            requester=self.client_user,
            client=self.org,
            status=status,
            sub_status=sub_status if status == S.IN_PROGRESS else None,
            assigned_developer=developer or self.dev,
            assigned_tester=tester,
        )

    # ── Dashboard ────────────────────────────────────────────────────────────

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_dashboard_requires_developer_role(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_shows_only_assigned_tickets(self):
        own   = self._make_ticket(developer=self.dev)
        other = self._make_ticket(developer=self.dev2)
        resp  = self.client.get(reverse("dev:dashboard"))
        self.assertEqual(resp.status_code, 200)
        ids = [t.pk for t in resp.context["assigned_tickets"]]
        self.assertIn(own.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_dashboard_context_counts(self):
        self._make_ticket(S.IN_PROGRESS, SS.DEVELOPMENT)
        self._make_ticket(S.AWAITING_CLIENT, sub_status=None)
        self._make_ticket(S.UAT, sub_status=None)
        self._make_ticket(S.RESOLVED, sub_status=None)
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertEqual(resp.status_code, 200)
        # active = in_progress + awaiting_client = 2
        self.assertEqual(resp.context["active_count"], 2)
        self.assertEqual(resp.context["forwarded_count"], 1)
        self.assertEqual(resp.context["uat_count"], 1)
        self.assertEqual(resp.context["resolved_closed_count"], 1)

    # ── Detail ───────────────────────────────────────────────────────────────

    def test_detail_requires_login(self):
        ticket = self._make_ticket()
        self.client.logout()
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_detail_requires_developer_role(self):
        ticket = self._make_ticket()
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_detail_own_ticket_ok(self):
        ticket = self._make_ticket()
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["ticket"].pk, ticket.pk)

    def test_detail_other_developers_ticket_is_404(self):
        other_ticket = self._make_ticket(developer=self.dev2)
        resp = self.client.get(reverse("dev:ticket_detail", args=[other_ticket.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_detail_context_booleans_submit_for_testing(self):
        tester = User.objects.create_user(
            "tester1", email="t1@test.local", password="pw", role="tester"
        )
        ticket = self._make_ticket(tester=tester)
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertTrue(resp.context["show_submit_for_testing"])
        self.assertFalse(resp.context["show_mark_ready"])
        self.assertFalse(resp.context["show_resubmit"])

    def test_detail_context_booleans_mark_ready(self):
        ticket = self._make_ticket()
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertFalse(resp.context["show_submit_for_testing"])
        self.assertTrue(resp.context["show_mark_ready"])
        self.assertFalse(resp.context["show_resubmit"])

    # ── Transitions ──────────────────────────────────────────────────────────

    def test_transition_mark_ready_no_tester(self):
        ticket = self._make_ticket()
        resp = self.client.post(
            reverse("dev:ticket_transition", args=[ticket.pk]),
            {"action": "mark_ready"},
        )
        self.assertRedirects(resp, reverse("dev:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.READY_FOR_UAT)

    def test_transition_submit_for_testing(self):
        tester = User.objects.create_user(
            "tester2", email="t2@test.local", password="pw", role="tester"
        )
        ticket = self._make_ticket(tester=tester)
        resp = self.client.post(
            reverse("dev:ticket_transition", args=[ticket.pk]),
            {"action": "submit_for_testing"},
        )
        self.assertRedirects(resp, reverse("dev:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.TESTING)

    def test_transition_invalid_action_blocked(self):
        ticket = self._make_ticket()
        resp = self.client.post(
            reverse("dev:ticket_transition", args=[ticket.pk]),
            {"action": "approve"},
        )
        self.assertRedirects(resp, reverse("dev:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.sub_status, SS.DEVELOPMENT)

    def test_transition_unassigned_ticket_is_404(self):
        other_ticket = self._make_ticket(developer=self.dev2)
        resp = self.client.post(
            reverse("dev:ticket_transition", args=[other_ticket.pk]),
            {"action": "mark_ready"},
        )
        self.assertEqual(resp.status_code, 404)

    # ── Form markup integrity ─────────────────────────────────────────────────

    def test_form_markup_submit_for_testing(self):
        tester = User.objects.create_user(
            "tester_m1", email="tm1@test.local", password="pw", role="tester"
        )
        ticket = self._make_ticket(tester=tester)
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        transition_url = reverse("dev:ticket_transition", args=[ticket.pk])
        self.assertIn(f'action="{transition_url}"', html)
        self.assertIn('name="action" value="submit_for_testing"', html)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_form_markup_mark_ready(self):
        ticket = self._make_ticket()
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        transition_url = reverse("dev:ticket_transition", args=[ticket.pk])
        self.assertIn(f'action="{transition_url}"', html)
        self.assertIn('name="action" value="mark_ready"', html)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_form_markup_resubmit_for_testing(self):
        tester = User.objects.create_user(
            "tester_m2", email="tm2@test.local", password="pw", role="tester"
        )
        ticket = self._make_ticket(sub_status=SS.RETURNED, tester=tester)
        resp = self.client.get(reverse("dev:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        transition_url = reverse("dev:ticket_transition", args=[ticket.pk])
        self.assertIn(f'action="{transition_url}"', html)
        self.assertIn('name="action" value="resubmit_for_testing"', html)
        self.assertIn("csrfmiddlewaretoken", html)
