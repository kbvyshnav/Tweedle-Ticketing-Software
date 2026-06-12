from django.contrib.auth import get_user_model
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
