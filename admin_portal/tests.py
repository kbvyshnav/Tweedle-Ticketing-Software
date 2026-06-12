from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.models import Ticket

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class AdminDashboardTemplateTests(TestCase):
    def setUp(self):
        self.url = reverse("admin_dashboard")
        self.admin = User.objects.create_user(
            "admin_t", email="admin_t@tweedle.local", password="pw", role="admin"
        )
        self.client_user = User.objects.create_user(
            "client_t", email="client_t@tweedle.local", password="pw", role="client"
        )

    def test_admin_gets_200_and_uses_templates(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin_portal/dashboard.html")
        self.assertTemplateUsed(resp, "base.html")

    def test_non_admin_forbidden(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class AdminDashboardDataBindingTests(TestCase):
    def setUp(self):
        self.url = reverse("admin_dashboard")
        self.admin = User.objects.create_user(
            "admin_d", email="admin_d@tweedle.local", password="pw", role="admin"
        )
        self.requester = User.objects.create_user(
            "client_d", email="client_d@tweedle.local", password="pw", role="client"
        )
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None):
        return Ticket.objects.create(
            subject=f"Ticket {status} {sub_status or ''}".strip(),
            requester=self.requester,
            client=self.org,
            status=status,
            sub_status=sub_status,
        )

    def test_each_ticket_lands_in_its_tab(self):
        tickets = {
            "inbox": self._make(S.NEW),
            "inprogress": self._make(S.IN_PROGRESS, SS.DEVELOPMENT),
            "forwarded": self._make(S.AWAITING_CLIENT),
            "uat": self._make(S.UAT),
            "resolved": self._make(S.RESOLVED),
            "closed": self._make(S.CLOSED),
            "rejected": self._make(S.REJECTED),
        }
        cancelled = self._make(S.CANCELLED)  # has no tab

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        for tab, ticket in tickets.items():
            ctx_list = list(resp.context[f"{tab}_tickets"])
            self.assertEqual(ctx_list, [ticket], f"{tab} tab should hold only its ticket")
            self.assertEqual(resp.context[f"{tab}_count"], 1)
            self.assertContains(resp, ticket.reference)

        # cancelled appears in no tab
        for tab in tickets:
            self.assertNotIn(cancelled, list(resp.context[f"{tab}_tickets"]))

    def test_counts_match_querysets(self):
        for _ in range(3):
            self._make(S.NEW)
        self._make(S.UAT)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["inbox_count"], 3)
        self.assertEqual(resp.context["inbox_count"], len(resp.context["inbox_tickets"]))
        self.assertEqual(resp.context["uat_count"], 1)
        self.assertEqual(resp.context["closed_count"], 0)

    def test_empty_tab_shows_empty_state(self):
        # No tickets at all -> every tab empty; empty-state rows render visible
        # (no display:none) and counts are zero.
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["inbox_count"], 0)
        self.assertContains(resp, 'id="emptyState-inbox"')
        # When empty, the row is NOT hidden.
        self.assertNotContains(
            resp, 'id="emptyState-inbox" class="tw-empty-state-row" style="display:none;"'
        )

    def test_stage_badge_reflects_sub_status(self):
        self._make(S.IN_PROGRESS, SS.READY_FOR_UAT)
        resp = self.client.get(self.url)
        self.assertContains(resp, "Ready for UAT")
        self.assertContains(resp, "tw-status-badge--testing-passed")

    def test_inbox_tab_heading_count_matches_queryset(self):
        # 2 inbox tickets -> the server-rendered heading shows "2 tickets",
        # not a stale hardcoded value.
        self._make(S.NEW)
        self._make(S.NEW)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["inbox_count"], 2)
        self.assertContains(resp, "2 tickets · New and unassigned")
        # The stale hardcoded heading must be gone.
        self.assertNotContains(resp, "10 tickets · New and unassigned")

    def test_inbox_heading_singular_for_one(self):
        self._make(S.NEW)
        resp = self.client.get(self.url)
        self.assertContains(resp, "1 ticket · New and unassigned")

    def test_stat_card_aria_label_reflects_count(self):
        self._make(S.NEW)
        self._make(S.NEW)
        self._make(S.UAT)
        resp = self.client.get(self.url)
        self.assertContains(resp, 'aria-label="Inbox: 2 tickets"')
        self.assertContains(resp, 'aria-label="UAT Approval: 1 ticket"')
        # The stale hardcoded value is gone.
        self.assertNotContains(resp, 'aria-label="Inbox: 10 tickets"')


class AdminTicketTransitionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "admin_x", email="admin_x@tweedle.local", password="pw", role="admin"
        )
        self.requester = User.objects.create_user(
            "client_x", email="client_x@tweedle.local", password="pw", role="client"
        )
        self.developer = User.objects.create_user(
            "dev_x", email="dev_x@tweedle.local", password="pw", role="developer"
        )
        self.tester = User.objects.create_user(
            "tester_x", email="tester_x@tweedle.local", password="pw", role="tester"
        )
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="A ticket",
            requester=self.requester,
            client=self.org,
            status=status,
            sub_status=sub_status,
            **kw,
        )

    def _url(self, ticket):
        return reverse("ticket_transition", args=[ticket.pk])

    def _errors(self, resp):
        return [m for m in resp.context["messages"] if m.level_tag == "error"]

    # ── happy paths ──────────────────────────────────────────────────────
    def test_assign_persists_assignees_and_writes_event(self):
        t = self._make(S.NEW)
        resp = self.client.post(
            self._url(t),
            {"action": "assign", "developer": self.developer.pk, "tester": self.tester.pk},
        )
        self.assertRedirects(resp, reverse("admin_dashboard"))
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertEqual(t.assigned_developer, self.developer)
        self.assertEqual(t.assigned_tester, self.tester)
        self.assertEqual(t.events.count(), 1)

    def test_reject_with_reason(self):
        t = self._make(S.NEW)
        self.client.post(self._url(t), {"action": "reject", "reason": "Duplicate"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.REJECTED)

    def test_resume_restores_paused_sub_status(self):
        t = self._make(
            S.AWAITING_CLIENT,
            paused_sub_status=SS.TESTING,
            assigned_developer=self.developer,
        )
        self.client.post(self._url(t), {"action": "resume"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.TESTING)

    def test_send_to_uat(self):
        t = self._make(S.IN_PROGRESS, SS.READY_FOR_UAT, assigned_developer=self.developer)
        self.client.post(self._url(t), {"action": "send_to_uat"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)

    # ── bad input is surfaced, never a 500, and changes nothing ──────────
    def test_assign_without_developer_surfaces_error(self):
        t = self._make(S.NEW)
        resp = self.client.post(self._url(t), {"action": "assign"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)
        self.assertEqual(t.events.count(), 0)
        self.assertTrue(self._errors(resp))

    def test_illegal_transition_surfaces_error_and_unchanged(self):
        t = self._make(S.NEW)  # send_to_uat is illegal from 'new'
        resp = self.client.post(self._url(t), {"action": "send_to_uat"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)
        self.assertEqual(t.events.count(), 0)
        self.assertTrue(self._errors(resp))

    def test_unsupported_action_surfaces_error(self):
        t = self._make(S.RESOLVED)  # 'close' is valid in the engine but not exposed here
        resp = self.client.post(self._url(t), {"action": "close"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.RESOLVED)
        self.assertTrue(self._errors(resp))

    # ── auth / CSRF ──────────────────────────────────────────────────────
    def test_non_admin_forbidden(self):
        t = self._make(S.NEW)
        self.client.force_login(self.requester)  # client role
        resp = self.client.post(self._url(t), {"action": "reject", "reason": "x"})
        self.assertEqual(resp.status_code, 403)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)

    def test_csrf_required(self):
        t = self._make(S.NEW)
        csrf_client = DjangoTestClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        resp = csrf_client.post(self._url(t), {"action": "reject", "reason": "x"})
        self.assertEqual(resp.status_code, 403)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)

    def test_get_not_allowed(self):
        t = self._make(S.NEW)
        self.assertEqual(self.client.get(self._url(t)).status_code, 405)
