from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Client
from tickets.models import Ticket
from tickets.transitions import REOPEN_WINDOW_DAYS

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class ClientPortalTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.other_org = Client.objects.create(name="Beta Inc", code="BETA")

        self.client_user = User.objects.create_user(
            "client_main",
            email="client_main@test.local",
            password="pw",
            role="client",
            client=self.org,
        )
        self.other_client = User.objects.create_user(
            "client_other",
            email="client_other@test.local",
            password="pw",
            role="client",
            client=self.other_org,
        )

        self.client.force_login(self.client_user)

    def _make_ticket(self, status, sub_status=None, org=None, requester=None, **kw):
        return Ticket.objects.create(
            subject="Test ticket",
            description="A description for testing.",
            requester=requester or self.client_user,
            client=org or self.org,
            status=status,
            sub_status=sub_status,
            **kw,
        )

    # ── Dashboard ────────────────────────────────────────────────────────────

    def test_dashboard_shows_only_own_org_tickets(self):
        own = self._make_ticket(S.NEW)
        other = self._make_ticket(S.NEW, org=self.other_org, requester=self.other_client)
        resp = self.client.get(reverse("client_dashboard"))
        self.assertEqual(resp.status_code, 200)
        ids = [t.pk for t in resp.context["tickets"]]
        self.assertIn(own.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_cancel_uses_confirm_overlay_not_native_confirm(self):
        # Confirm-UX standardization: the new-ticket Cancel routes through the
        # styled overlay, not the browser-native confirm().
        t = self._make_ticket(S.NEW)
        resp = self.client.get(reverse("client_ticket_detail", args=[t.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cancelConfirmOverlay")
        self.assertContains(resp, "openCancelConfirm(")
        self.assertNotContains(resp, "confirm('Cancel this ticket?')")

    # ── Detail ───────────────────────────────────────────────────────────────

    def test_detail_404_for_other_org_ticket(self):
        other = self._make_ticket(S.NEW, org=self.other_org, requester=self.other_client)
        resp = self.client.get(reverse("client_ticket_detail", args=[other.pk]))
        self.assertEqual(resp.status_code, 404)

    # ── Submit ───────────────────────────────────────────────────────────────

    def test_ticket_creation_valid_post(self):
        count_before = Ticket.objects.filter(client=self.org).count()
        resp = self.client.post(
            reverse("client_submit_ticket"),
            {
                "subject": "New Feature Request",
                "description": "This is a detailed description of the feature request.",
                "category": "Feature",
                "priority": "medium",
            },
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        self.assertEqual(Ticket.objects.filter(client=self.org).count(), count_before + 1)
        created = Ticket.objects.filter(client=self.org).order_by("-created_at").first()
        self.assertEqual(created.status, S.NEW)
        self.assertEqual(created.requester, self.client_user)

    def test_ticket_creation_missing_subject(self):
        count_before = Ticket.objects.count()
        resp = self.client.post(
            reverse("client_submit_ticket"),
            {
                "subject": "",
                "description": "This is a detailed description of the bug.",
                "category": "Bug",
                "priority": "high",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Ticket.objects.count(), count_before)

    def test_ticket_creation_missing_description(self):
        count_before = Ticket.objects.count()
        resp = self.client.post(
            reverse("client_submit_ticket"),
            {
                "subject": "Some ticket",
                "description": "",
                "category": "Bug",
                "priority": "medium",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Ticket.objects.count(), count_before)

    # ── Transitions ──────────────────────────────────────────────────────────

    def test_approve_uat_ticket(self):
        ticket = self._make_ticket(S.UAT)
        resp = self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "approve"},
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.RESOLVED)

    def test_request_changes_uat_ticket(self):
        ticket = self._make_ticket(S.UAT)
        resp = self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "request_changes", "feedback": "Please fix the login button."},
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.IN_PROGRESS)
        self.assertEqual(ticket.sub_status, SS.DEVELOPMENT)

    def test_cancel_new_ticket(self):
        ticket = self._make_ticket(S.NEW)
        resp = self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "cancel"},
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.CANCELLED)

    def test_reopen_resolved_ticket(self):
        ticket = self._make_ticket(S.RESOLVED)
        resp = self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "reopen", "reason": "Issue has recurred."},
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.IN_PROGRESS)
        self.assertEqual(ticket.sub_status, SS.DEVELOPMENT)

    def test_reopen_closed_ticket_within_window(self):
        ticket = self._make_ticket(
            S.CLOSED,
            closed_at=timezone.now() - timedelta(days=3),
        )
        resp = self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "reopen", "reason": "Still broken."},
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.IN_PROGRESS)

    def test_reopen_closed_ticket_outside_window(self):
        ticket = self._make_ticket(
            S.CLOSED,
            closed_at=timezone.now() - timedelta(days=REOPEN_WINDOW_DAYS + 16),
        )
        self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "reopen", "reason": "Need it reopened."},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.CLOSED)

    def test_transition_endpoint_404_for_other_org_ticket(self):
        other = self._make_ticket(S.UAT, org=self.other_org, requester=self.other_client)
        resp = self.client.post(
            reverse("client_ticket_transition", args=[other.pk]),
            {"action": "approve"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_disallowed_action_rejected(self):
        ticket = self._make_ticket(S.NEW)
        self.client.post(
            reverse("client_ticket_transition", args=[ticket.pk]),
            {"action": "assign"},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.NEW)
