from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.models import Ticket

User = get_user_model()
S  = Ticket.Status
SS = Ticket.SubStatus


class SubuserPortalTests(TestCase):
    def setUp(self):
        self.org       = Client.objects.create(name="Acme Corp", code="ACME")
        self.other_org = Client.objects.create(name="Beta Inc",  code="BETA")

        self.subuser = User.objects.create_user(
            "subuser1", email="subuser1@test.local", password="pw",
            role="subuser", client=self.org,
        )
        # Second subuser in same org — used for scope / guard tests
        self.subuser2 = User.objects.create_user(
            "subuser2", email="subuser2@test.local", password="pw",
            role="subuser", client=self.org,
        )
        # Non-subuser for role-guard tests
        self.admin_user = User.objects.create_user(
            "admin1", email="admin1@test.local", password="pw", role="admin",
        )

        self.client.force_login(self.subuser)

    def _make_ticket(self, status=S.NEW, sub_status=None, requester=None, org=None, **kw):
        return Ticket.objects.create(
            subject="Test ticket",
            description="A description for testing purposes.",
            requester=requester or self.subuser,
            client=org or self.org,
            status=status,
            sub_status=sub_status,
            **kw,
        )

    # ── Auth / access control ─────────────────────────────────────────────────

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("subuser:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_dashboard_requires_subuser_role(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("subuser:dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_detail_requires_login(self):
        ticket = self._make_ticket()
        self.client.logout()
        resp = self.client.get(reverse("subuser:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_detail_requires_subuser_role(self):
        ticket = self._make_ticket()
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("subuser:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_submit_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("subuser:submit_ticket"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_transition_endpoint_rejects_get(self):
        ticket = self._make_ticket(S.UAT)
        resp = self.client.get(reverse("subuser:ticket_transition", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 405)

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def test_dashboard_shows_only_own_tickets(self):
        own   = self._make_ticket(S.NEW)
        other = self._make_ticket(S.NEW, requester=self.subuser2)
        resp  = self.client.get(reverse("subuser:dashboard"))
        self.assertEqual(resp.status_code, 200)
        ids = [t.pk for t in resp.context["tickets"]]
        self.assertIn(own.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_dashboard_context_counts(self):
        self._make_ticket(S.NEW)
        self._make_ticket(S.IN_PROGRESS, SS.DEVELOPMENT)
        self._make_ticket(S.UAT)
        self._make_ticket(S.AWAITING_CLIENT)
        self._make_ticket(S.RESOLVED)
        self._make_ticket(S.CLOSED)
        resp = self.client.get(reverse("subuser:dashboard"))
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertEqual(ctx["open_count"],         4)   # new + in_progress + uat + awaiting_client
        self.assertEqual(ctx["needs_action_count"], 2)   # uat + awaiting_client
        self.assertEqual(ctx["resolved_count"],     1)
        self.assertEqual(ctx["closed_count"],       1)

    # ── Detail ────────────────────────────────────────────────────────────────

    def test_detail_own_ticket_ok(self):
        ticket = self._make_ticket()
        resp = self.client.get(reverse("subuser:ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["ticket"].pk, ticket.pk)

    def test_detail_other_users_ticket_is_404(self):
        other_ticket = self._make_ticket(requester=self.subuser2)
        resp = self.client.get(reverse("subuser:ticket_detail", args=[other_ticket.pk]))
        self.assertEqual(resp.status_code, 404)

    # ── Submit ticket ─────────────────────────────────────────────────────────

    def test_submit_get_returns_200(self):
        resp = self.client.get(reverse("subuser:submit_ticket"))
        self.assertEqual(resp.status_code, 200)

    def test_submit_valid_post_creates_ticket(self):
        count_before = Ticket.objects.filter(requester=self.subuser).count()
        resp = self.client.post(
            reverse("subuser:submit_ticket"),
            {
                "subject":     "Export button is broken",
                "description": "When I click export the file is empty every time.",
                "category":    "Bug",
                "priority":    "high",
            },
        )
        self.assertRedirects(resp, reverse("subuser:dashboard"))
        self.assertEqual(
            Ticket.objects.filter(requester=self.subuser).count(),
            count_before + 1,
        )
        created = Ticket.objects.filter(requester=self.subuser).order_by("-created_at").first()
        self.assertEqual(created.status, S.NEW)
        self.assertEqual(created.client, self.org)

    def test_submit_missing_subject_rerenders(self):
        count_before = Ticket.objects.count()
        resp = self.client.post(
            reverse("subuser:submit_ticket"),
            {
                "subject":     "",
                "description": "A long enough description here for the form.",
                "category":    "Bug",
                "priority":    "medium",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Ticket.objects.count(), count_before)

    def test_submit_short_description_rerenders(self):
        count_before = Ticket.objects.count()
        resp = self.client.post(
            reverse("subuser:submit_ticket"),
            {
                "subject":     "Short description test",
                "description": "Too short.",
                "category":    "Bug",
                "priority":    "medium",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Ticket.objects.count(), count_before)

    def test_submit_empty_category_rerenders(self):
        count_before = Ticket.objects.count()
        resp = self.client.post(
            reverse("subuser:submit_ticket"),
            {
                "subject":     "No category ticket",
                "description": "This is a long enough description for the form validation.",
                "category":    "",
                "priority":    "medium",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Ticket.objects.count(), count_before)

    # ── Transitions — confirm ─────────────────────────────────────────────────

    def test_confirm_on_uat_ticket_sets_flag(self):
        ticket = self._make_ticket(S.UAT)
        resp = self.client.post(
            reverse("subuser:ticket_transition", args=[ticket.pk]),
            {"action": "confirm"},
        )
        self.assertRedirects(resp, reverse("subuser:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertTrue(ticket.subuser_confirmed)
        self.assertEqual(ticket.status, S.UAT)  # status unchanged by confirm

    def test_confirm_on_non_uat_ticket_fails(self):
        ticket = self._make_ticket(S.NEW)
        self.client.post(
            reverse("subuser:ticket_transition", args=[ticket.pk]),
            {"action": "confirm"},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.NEW)

    # ── Transitions — request_changes ────────────────────────────────────────

    def test_request_changes_with_feedback_returns_to_dev(self):
        ticket = self._make_ticket(S.UAT)
        resp = self.client.post(
            reverse("subuser:ticket_transition", args=[ticket.pk]),
            {"action": "request_changes", "feedback": "The export still downloads an empty CSV."},
        )
        self.assertRedirects(resp, reverse("subuser:ticket_detail", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.IN_PROGRESS)
        self.assertEqual(ticket.sub_status, SS.DEVELOPMENT)

    def test_request_changes_without_feedback_fails(self):
        ticket = self._make_ticket(S.UAT)
        self.client.post(
            reverse("subuser:ticket_transition", args=[ticket.pk]),
            {"action": "request_changes", "feedback": ""},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.UAT)

    def test_request_changes_non_requester_blocked_by_engine(self):
        """
        subuser2 is a same-org user who is NOT the requester.
        The transition endpoint finds the ticket (org-level lookup),
        but guard_request_changes / _require_requester_or_admin raises
        TransitionNotAllowed before any status change occurs.
        Non-empty feedback is supplied so required_fields validation passes first.
        """
        ticket = self._make_ticket(S.UAT, requester=self.subuser)
        self.client.force_login(self.subuser2)
        self.client.post(
            reverse("subuser:ticket_transition", args=[ticket.pk]),
            {"action": "request_changes", "feedback": "Still broken after the latest release."},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.UAT)

    def test_transition_disallowed_action_blocked(self):
        ticket = self._make_ticket(S.UAT)
        resp = self.client.post(
            reverse("subuser:ticket_transition", args=[ticket.pk]),
            {"action": "approve"},
        )
        self.assertRedirects(resp, reverse("subuser:dashboard"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, S.UAT)
