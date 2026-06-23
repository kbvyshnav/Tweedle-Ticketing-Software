from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from notifications.models import Notification
from tickets.models import Ticket, TicketEvent, TicketMessage
from tickets.transitions import transition

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

    def test_orphaned_modals_removed_from_dashboard(self):
        # Sweep S1/S2: the orphaned #newTicketModal / #rejectedTicketModal are gone,
        # along with their hardcoded fake data and the dead workload-stat JS refs (S6).
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        # dead markup removed
        self.assertNotContains(resp, 'id="newTicketModal"')
        self.assertNotContains(resp, 'id="rejectedTicketModal"')
        # hardcoded fakes removed
        self.assertNotContains(resp, "Rahul R Nair")
        self.assertNotContains(resp, "wallet_specs.pdf")
        self.assertNotContains(resp, "TKT-00089")
        # dead JS refs (S6 leftover) removed
        self.assertNotContains(resp, "showDeveloperInfo")
        self.assertNotContains(resp, "showTesterInfo")
        # live path intact: the real detail modal shell still ships
        self.assertContains(resp, 'id="ticketDetailsModal"')


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

    def test_server_empty_tab_shows_status_message_not_filter_message(self):
        # A genuinely empty status shows the per-tab status text; the filter
        # message exists in the DOM but is the hidden (display:none) one.
        resp = self.client.get(self.url)
        self.assertContains(resp, "No tickets in the inbox.")
        self.assertContains(resp, "Nothing awaiting client response.")
        self.assertContains(resp, "No rejected tickets.")
        # The filter text is present but hidden by default.
        self.assertContains(
            resp,
            'class="tw-empty-filter" style="color:var(--tw-text-muted);'
            'font-size:var(--tw-text-base);margin:0;display:none;"',
        )

    def test_empty_state_spans_full_width(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, '<td colspan="9"')

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
        self.assertEqual(t.events.exclude(action="submitted").count(), 1)

    def test_assign_success_message_is_human_friendly(self):
        t = self._make(S.NEW)
        resp = self.client.post(
            self._url(t), {"action": "assign", "developer": self.developer.pk}, follow=True
        )
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(
            any(f"Ticket {t.reference} assigned to {self.developer.username}." == m for m in msgs),
            msgs,
        )

    def test_reject_with_reason(self):
        t = self._make(S.NEW)
        resp = self.client.post(
            self._url(t), {"action": "reject", "reason": "Duplicate"}, follow=True
        )
        t.refresh_from_db()
        self.assertEqual(t.status, S.REJECTED)
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertIn(f"Ticket {t.reference} rejected.", msgs)

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
        self.assertEqual(t.events.exclude(action="submitted").count(), 0)
        self.assertTrue(self._errors(resp))

    def test_illegal_transition_surfaces_error_and_unchanged(self):
        t = self._make(S.NEW)  # send_to_uat is illegal from 'new'
        resp = self.client.post(self._url(t), {"action": "send_to_uat"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)
        self.assertEqual(t.events.exclude(action="submitted").count(), 0)
        self.assertTrue(self._errors(resp))

    def test_unsupported_action_surfaces_error(self):
        # 'approve' is a real engine action but is NOT exposed by this admin
        # endpoint (it's a client/requester action). cancel/reopen/restore ARE
        # now exposed — see AdminCancelTests / AdminReopenRestoreTests.
        t = self._make(S.UAT, assigned_developer=self.developer)
        resp = self.client.post(self._url(t), {"action": "approve"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)
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

    # ── 4.3 modal actions ────────────────────────────────────────────────
    def test_request_info(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        self.client.post(
            self._url(t), {"action": "request_info", "message": "Need the account no."}
        )
        t.refresh_from_db()
        self.assertEqual(t.status, S.AWAITING_CLIENT)
        self.assertEqual(t.paused_sub_status, SS.DEVELOPMENT)

    def test_reassign_changes_developer_without_status_change(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        other = User.objects.create_user("dev2", role="developer")
        self.client.post(self._url(t), {"action": "reassign", "developer": other.pk})
        t.refresh_from_db()
        self.assertEqual(t.assigned_developer, other)
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)

    def test_recall_request_changes_from_uat(self):
        t = self._make(S.UAT, assigned_developer=self.developer)
        self.client.post(
            self._url(t), {"action": "request_changes", "feedback": "Still wrong"}
        )
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)

    def test_close_from_resolved(self):
        t = self._make(S.RESOLVED, assigned_developer=self.developer)
        self.client.post(self._url(t), {"action": "close"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.CLOSED)
        self.assertIsNotNone(t.closed_at)

    def test_close_illegal_on_in_progress(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        resp = self.client.post(self._url(t), {"action": "close"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.events.exclude(action="submitted").count(), 0)
        self.assertTrue(self._errors(resp))

    def test_request_info_without_message_errors(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        resp = self.client.post(self._url(t), {"action": "request_info"}, follow=True)
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertTrue(self._errors(resp))


class AdminTicketDetailTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin_dt", role="admin")
        self.requester = User.objects.create_user("client_dt", role="client")
        self.developer = User.objects.create_user("dev_dt", role="developer")
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="Login is broken",
            description="Steps to reproduce…",
            requester=self.requester,
            client=self.org,
            status=status,
            sub_status=sub_status,
            **kw,
        )

    def _url(self, t):
        return reverse("admin_ticket_detail", args=[t.pk])

    def test_detail_shows_fields_only_no_timeline_or_chat(self):
        # 4.3b: timeline + chat moved to their own drawers; the detail modal
        # shows details + actions only, and must not leak the stray comment.
        t = self._make(S.NEW)
        transition(t, "assign", self.admin, developer=self.developer)
        TicketMessage.objects.create(ticket=t, author=self.requester, body="Any update?")
        resp = self.client.get(self._url(t))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin_portal/_ticket_detail.html")
        self.assertContains(resp, t.reference)
        self.assertContains(resp, "Login is broken")
        # No timeline/chat sections in the detail partial anymore.
        self.assertNotContains(resp, '<h3 class="section-title">Timeline</h3>')
        self.assertNotContains(resp, '<h3 class="section-title">Chat</h3>')
        self.assertNotContains(resp, "Any update?")
        # The stray multi-line {# #} comment must not render as text.
        self.assertNotContains(resp, "Injected into")

    def test_non_admin_forbidden(self):
        t = self._make(S.NEW)
        self.client.force_login(self.requester)
        self.assertEqual(self.client.get(self._url(t)).status_code, 403)

    # ── button visibility mirrors the engine ─────────────────────────────
    def test_resolved_shows_only_close(self):
        t = self._make(S.RESOLVED, assigned_developer=self.developer)
        resp = self.client.get(self._url(t))
        self.assertContains(resp, 'name="action" value="close"')
        self.assertNotContains(resp, 'value="request_info"')
        self.assertNotContains(resp, 'value="request_changes"')
        self.assertNotContains(resp, 'value="reassign"')

    def test_uat_shows_only_recall(self):
        t = self._make(S.UAT, assigned_developer=self.developer)
        resp = self.client.get(self._url(t))
        self.assertContains(resp, 'name="action" value="request_changes"')
        self.assertNotContains(resp, 'value="close"')
        self.assertNotContains(resp, 'value="request_info"')
        self.assertNotContains(resp, 'value="reassign"')

    def test_in_progress_shows_request_info_and_reassign_not_close(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        resp = self.client.get(self._url(t))
        self.assertContains(resp, 'name="action" value="request_info"')
        self.assertContains(resp, 'name="action" value="reassign"')
        self.assertNotContains(resp, 'value="close"')
        self.assertNotContains(resp, 'value="request_changes"')

    def test_awaiting_client_shows_resume_and_reassign_not_request_info(self):
        t = self._make(S.AWAITING_CLIENT, paused_sub_status=SS.DEVELOPMENT,
                       assigned_developer=self.developer)
        resp = self.client.get(self._url(t))
        self.assertContains(resp, 'name="action" value="resume"')
        self.assertContains(resp, 'name="action" value="reassign"')
        self.assertNotContains(resp, 'value="request_info"')

    def test_closed_shows_reopen_only(self):
        # Closed is no longer read-only: admin can reopen (Step 4). The other
        # action forms must still be absent.
        t = self._make(S.CLOSED, assigned_developer=self.developer)
        resp = self.client.get(self._url(t))
        self.assertContains(resp, 'name="action" value="reopen"')
        self.assertNotContains(resp, 'value="close"')
        self.assertNotContains(resp, 'value="request_info"')
        self.assertNotContains(resp, 'value="request_changes"')


class AdminTicketDrawerTests(TestCase):
    """Timeline + chat drawers (Phase 4.3b)."""

    def setUp(self):
        self.admin = User.objects.create_user("admin_dr", role="admin")
        self.requester = User.objects.create_user("client_dr", role="client")
        self.developer = User.objects.create_user("dev_dr", role="developer")
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self):
        return Ticket.objects.create(
            subject="Login is broken", requester=self.requester, client=self.org,
            status=S.NEW,
        )

    def test_timeline_drawer_renders_real_events(self):
        t = self._make()
        transition(t, "assign", self.admin, developer=self.developer)  # writes an event
        resp = self.client.get(reverse("admin_ticket_timeline", args=[t.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin_portal/_ticket_timeline.html")
        self.assertContains(resp, "assign")          # the event action
        self.assertContains(resp, self.admin.username)

    def test_timeline_meta_uses_friendly_status_labels(self):
        # S9: the from→to meta line must show friendly labels, not raw codes.
        t = self._make()
        transition(t, "assign", self.admin, developer=self.developer)
        resp = self.client.get(reverse("admin_ticket_timeline", args=[t.pk]))
        # assign: new → in_progress / development
        self.assertContains(resp, "In Progress")
        self.assertContains(resp, "Development")
        # the raw code must not appear in the from→to meta line
        self.assertNotContains(resp, "in_progress / development")

    def test_chat_drawer_renders_real_messages_readonly(self):
        t = self._make()
        TicketMessage.objects.create(ticket=t, author=self.requester, body="Any update?")
        resp = self.client.get(reverse("admin_ticket_chat", args=[t.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin_portal/_ticket_chat.html")
        self.assertContains(resp, "Any update?")
        self.assertContains(resp, self.requester.username)
        # Read-only: the partial carries no compose form/textarea.
        self.assertNotContains(resp, "<textarea")

    def test_timeline_drawer_admin_only(self):
        t = self._make()
        self.client.force_login(self.requester)
        self.assertEqual(
            self.client.get(reverse("admin_ticket_timeline", args=[t.pk])).status_code, 403
        )

    def test_chat_drawer_admin_only(self):
        t = self._make()
        self.client.force_login(self.requester)
        self.assertEqual(
            self.client.get(reverse("admin_ticket_chat", args=[t.pk])).status_code, 403
        )


class AdminReopenRestoreTests(TestCase):
    """Step 4: admin reopen (resolved/closed) + restore (rejected) wired into UI.

    Engine-level transition correctness is covered in tickets/tests.py; here we
    cover the admin endpoint whitelist/data-extraction and the detail-partial
    control gating.
    """

    def setUp(self):
        self.admin = User.objects.create_user("admin_rr", role="admin")
        self.requester = User.objects.create_user("client_rr", role="client")
        self.developer = User.objects.create_user("dev_rr", role="developer")
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="A ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def _url(self, t):
        return reverse("ticket_transition", args=[t.pk])

    def _detail_url(self, t):
        return reverse("admin_ticket_detail", args=[t.pk])

    def _errors(self, resp):
        return [m for m in resp.context["messages"] if m.level_tag == "error"]

    # ── view-level: reopen / restore through the admin endpoint ───────────
    def test_reopen_from_resolved(self):
        t = self._make(S.RESOLVED, assigned_developer=self.developer)
        self.client.post(self._url(t), {"action": "reopen", "reason": "Bug came back"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertEqual(t.assigned_developer, self.developer)  # re-routed to original dev
        self.assertEqual(t.events.filter(action="reopen").count(), 1)

    def test_reopen_from_closed(self):
        t = self._make(S.CLOSED, assigned_developer=self.developer)
        self.client.post(self._url(t), {"action": "reopen", "reason": "Regression"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertEqual(t.assigned_developer, self.developer)
        self.assertEqual(t.events.filter(action="reopen").count(), 1)

    def test_reopen_without_reason_is_rejected(self):
        t = self._make(S.RESOLVED, assigned_developer=self.developer)
        resp = self.client.post(
            self._url(t), {"action": "reopen", "reason": ""}, follow=True
        )
        t.refresh_from_db()
        self.assertEqual(t.status, S.RESOLVED)  # unchanged
        self.assertTrue(self._errors(resp))

    def test_restore_from_rejected(self):
        t = self._make(S.REJECTED)
        self.client.post(self._url(t), {"action": "restore"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)
        self.assertIsNone(t.sub_status)
        self.assertEqual(t.events.filter(action="restore").count(), 1)

    # ── detail-partial render gating ─────────────────────────────────────
    def test_resolved_shows_reopen_and_close(self):
        t = self._make(S.RESOLVED, assigned_developer=self.developer)
        resp = self.client.get(self._detail_url(t))
        self.assertContains(resp, 'name="action" value="reopen"')
        self.assertContains(resp, 'name="action" value="close"')

    def test_closed_shows_reopen(self):
        t = self._make(S.CLOSED, assigned_developer=self.developer)
        resp = self.client.get(self._detail_url(t))
        self.assertContains(resp, 'name="action" value="reopen"')

    def test_rejected_shows_restore(self):
        t = self._make(S.REJECTED)
        resp = self.client.get(self._detail_url(t))
        self.assertContains(resp, 'name="action" value="restore"')

    def test_reopen_restore_absent_where_not_applicable(self):
        for status, sub in [(S.NEW, None), (S.IN_PROGRESS, SS.DEVELOPMENT), (S.UAT, None)]:
            t = self._make(status, sub, assigned_developer=self.developer)
            resp = self.client.get(self._detail_url(t))
            self.assertNotContains(resp, 'value="reopen"', msg_prefix=str(status))
            self.assertNotContains(resp, 'value="restore"', msg_prefix=str(status))


class AdminCancelTests(TestCase):
    """Step 5: admin Cancel (T3) + the Cancelled tab.

    Engine-level cancel correctness is covered in tickets/tests.py; here we cover
    the admin endpoint whitelist/optional-reason extraction, the dashboard
    Cancelled-tab context/render, and the detail-partial control gating.
    """

    def setUp(self):
        self.admin = User.objects.create_user("admin_cx", role="admin")
        self.requester = User.objects.create_user("client_cx", role="client")
        self.developer = User.objects.create_user("dev_cx", role="developer")
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="A ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def _url(self, t):
        return reverse("ticket_transition", args=[t.pk])

    def _detail_url(self, t):
        return reverse("admin_ticket_detail", args=[t.pk])

    # ── view-level cancel from each legal state ──────────────────────────
    def test_cancel_from_new_without_reason(self):
        t = self._make(S.NEW)
        self.client.post(self._url(t), {"action": "cancel"})  # no reason (optional)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)
        self.assertEqual(t.events.filter(action="cancel").count(), 1)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.requester, ticket=t, action="cancel"
            ).exists()
        )

    def test_cancel_from_in_progress_with_reason(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        self.client.post(self._url(t), {"action": "cancel", "reason": "Duplicate"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)
        self.assertIsNone(t.sub_status)
        self.assertEqual(t.events.filter(action="cancel").first().note, "Duplicate")

    def test_cancel_from_awaiting_client_without_reason(self):
        t = self._make(S.AWAITING_CLIENT)
        self.client.post(self._url(t), {"action": "cancel"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)

    # ── dashboard Cancelled-tab context + render ─────────────────────────
    def test_dashboard_includes_cancelled_context(self):
        t = self._make(S.CANCELLED)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.context["cancelled_count"], 1)
        self.assertIn(t.pk, [x.pk for x in resp.context["cancelled_tickets"]])

    def test_cancelled_tab_renders_ticket_with_badge(self):
        t = self._make(S.CANCELLED)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertContains(resp, 'id="tab-cancelled"')
        self.assertContains(resp, t.reference)
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--rejected">Cancelled</span>',
        )

    def test_cancelled_tab_empty_state_when_none(self):
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.context["cancelled_count"], 0)
        # Empty-state row is rendered visible (no display:none) when none match.
        self.assertContains(
            resp, 'id="emptyState-cancelled" class="tw-empty-state-row">'
        )

    # ── detail-partial control gating ────────────────────────────────────
    def test_cancel_shows_on_in_progress_and_awaiting_client(self):
        for status, sub in [(S.IN_PROGRESS, SS.DEVELOPMENT), (S.AWAITING_CLIENT, None)]:
            t = self._make(status, sub, assigned_developer=self.developer)
            resp = self.client.get(self._detail_url(t))
            self.assertContains(resp, 'name="action" value="cancel"', msg_prefix=str(status))

    def test_cancelled_detail_is_read_only(self):
        t = self._make(S.CANCELLED)
        resp = self.client.get(self._detail_url(t))
        self.assertNotContains(resp, 'name="action"')
        self.assertContains(resp, "This ticket was cancelled")


class AdminNewTicketDetailTests(TestCase):
    """Step B: new tickets open the real detail partial (not the static modal),
    with relocated Assign/Reject; send_to_uat is in the modal at ready_for_uat.
    """

    def setUp(self):
        self.admin = User.objects.create_user("admin_nt", role="admin")
        self.requester = User.objects.create_user("client_nt", role="client")
        self.developer = User.objects.create_user("dev_nt", role="developer")
        self.tester = User.objects.create_user("tester_nt", role="tester")
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.requester.client = self.org
        self.requester.save(update_fields=["client"])
        self.client.force_login(self.admin)

    def _make(self, status=S.NEW, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="Federal API failing", description="500s on payment webhook.",
            category="Integration", priority="high",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def _detail(self, t):
        return reverse("admin_ticket_detail", args=[t.pk])

    def _transition(self, t):
        return reverse("ticket_transition", args=[t.pk])

    def test_new_detail_renders_real_data_and_assign_reject(self):
        t = self._make()
        resp = self.client.get(self._detail(t))
        self.assertEqual(resp.status_code, 200)
        # real, per-ticket data (not the old hardcoded modal placeholders)
        self.assertContains(resp, "Federal API failing")
        self.assertContains(resp, self.requester.username)
        self.assertContains(resp, "GMEC")
        self.assertContains(resp, "tw-priority-badge--high")
        # relocated assign / reject controls
        self.assertContains(resp, 'name="action" value="assign"')
        self.assertContains(resp, 'name="action" value="reject"')
        # the old static modal fakes never appear in the partial
        self.assertNotContains(resp, "Rahul R Nair")
        self.assertNotContains(resp, "wallet_specs.pdf")

    def test_new_ticket_timeline_drawer_shows_submitted(self):
        t = self._make()
        resp = self.client.get(reverse("admin_ticket_timeline", args=[t.pk]))
        self.assertContains(resp, "Ticket Submitted")

    def test_assign_from_partial_posts_and_transitions(self):
        t = self._make()
        self.client.post(self._transition(t), {
            "action": "assign", "developer": self.developer.pk, "tester": self.tester.pk,
        })
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertEqual(t.assigned_developer, self.developer)
        self.assertEqual(t.assigned_tester, self.tester)

    def test_reject_from_partial_posts_and_transitions(self):
        t = self._make()
        self.client.post(self._transition(t), {"action": "reject", "reason": "Out of scope"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.REJECTED)

    def test_ready_for_uat_detail_shows_send_to_uat(self):
        t = self._make(status=S.IN_PROGRESS, sub_status=SS.READY_FOR_UAT,
                       assigned_developer=self.developer)
        resp = self.client.get(self._detail(t))
        self.assertContains(resp, 'name="action" value="send_to_uat"')

    def test_development_detail_has_no_send_to_uat(self):
        t = self._make(status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT,
                       assigned_developer=self.developer)
        resp = self.client.get(self._detail(t))
        self.assertNotContains(resp, 'value="send_to_uat"')


class AdminConfirmHookTests(TestCase):
    """Step C: every admin modal action routes through the custom confirm box.

    These assert the confirm HOOK is present in the partial (and the underlying
    POST still transitions). The visual confirm behavior — box appears, input
    echoed, Cancel aborts, Confirm acts — needs BROWSER verification; the Django
    test client does not run JS.
    """

    def setUp(self):
        self.admin = User.objects.create_user("admin_ch", role="admin")
        self.requester = User.objects.create_user("client_ch", role="client")
        self.developer = User.objects.create_user("dev_ch", role="developer")
        self.tester = User.objects.create_user("tester_ch", role="tester")
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.client.force_login(self.admin)

    def _make(self, status=S.NEW, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="A ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def _detail(self, t):
        return self.client.get(reverse("admin_ticket_detail", args=[t.pk]))

    def _txn(self, t):
        return reverse("ticket_transition", args=[t.pk])

    # ── hook presence per action ─────────────────────────────────────────
    def test_new_keeps_assign_and_reject_helpers(self):
        resp = self._detail(self._make(S.NEW))
        self.assertContains(resp, "confirmAssignDetail")
        self.assertContains(resp, "confirmRejectDetail")

    def test_awaiting_client_resume_reassign_cancel_hooked(self):
        t = self._make(S.AWAITING_CLIENT, assigned_developer=self.developer)
        resp = self._detail(t)
        self.assertContains(resp, "confirmDetailAction(event, {title:'Resume Ticket'")
        self.assertContains(resp, "confirmDetailAction(event, {reassign:true")
        self.assertContains(resp, "optional:true, type:'danger', title:'Cancel Ticket'")
        self.assertNotContains(resp, 'onclick="return confirm(')  # native confirm gone

    def test_in_progress_request_info_reassign_cancel_hooked(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        resp = self._detail(t)
        self.assertContains(resp, "{field:'message', title:'Request Info'")
        self.assertContains(resp, "confirmDetailAction(event, {reassign:true")
        self.assertContains(resp, "title:'Cancel Ticket'")
        self.assertNotContains(resp, 'onclick="return confirm(')

    def test_uat_request_changes_hooked(self):
        resp = self._detail(self._make(S.UAT, assigned_developer=self.developer))
        self.assertContains(resp, "{field:'feedback', title:'Recall to In Progress'")

    def test_resolved_reopen_and_close_hooked(self):
        resp = self._detail(self._make(S.RESOLVED, assigned_developer=self.developer))
        self.assertContains(resp, "title:'Reopen Ticket'")
        self.assertContains(resp, "{type:'danger', title:'Close Ticket'")

    def test_closed_reopen_hooked(self):
        resp = self._detail(self._make(S.CLOSED, assigned_developer=self.developer))
        self.assertContains(resp, "title:'Reopen Ticket'")

    def test_rejected_restore_hooked(self):
        resp = self._detail(self._make(S.REJECTED))
        self.assertContains(resp, "title:'Restore Ticket'")

    # ── no-regression: the underlying POSTs still transition ─────────────
    def test_close_post_still_transitions(self):
        t = self._make(S.RESOLVED, assigned_developer=self.developer)
        self.client.post(self._txn(t), {"action": "close"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.CLOSED)

    def test_cancel_post_still_transitions(self):
        t = self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        self.client.post(self._txn(t), {"action": "cancel", "reason": "Duplicate"})
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)


class AdminWorkloadStatsTests(TestCase):
    """Issue 1b: dev/tester workload counts annotated onto the Assign/Reassign
    dropdown <option>s by admin_ticket_detail.

    These cover the annotation math + data-attr render. The on-change panel fill
    is browser-verified — the Django test client runs no JS.
    """

    def setUp(self):
        self.admin = User.objects.create_user("admin_wl", role="admin")
        self.requester = User.objects.create_user("client_wl", role="client")
        self.org = Client.objects.create(name="Workload", code="WLOD")
        self.dev = User.objects.create_user("dev_wl", role="developer")
        self.dev2 = User.objects.create_user("dev_wl2", role="developer")
        self.tester = User.objects.create_user("tester_wl", role="tester")
        self.tester2 = User.objects.create_user("tester_wl2", role="tester")
        # Any ticket gives us a URL; it carries no assignment so it adds no counts.
        self.anchor = self._make(S.NEW)
        self.url = reverse("admin_ticket_detail", args=[self.anchor.pk])
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, dev=None, tester=None):
        return Ticket.objects.create(
            subject=f"WL {status} {sub_status or ''}".strip(),
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status,
            assigned_developer=dev, assigned_tester=tester,
        )

    def _dev(self, resp, username):
        return {d.username: d for d in resp.context["developers"]}[username]

    def _tester(self, resp, username):
        return {t.username: t for t in resp.context["testers"]}[username]

    def test_developer_workload_counts(self):
        # active = in_progress + awaiting_client; in_dev = in_progress·{development,returned};
        # in_uat = uat. resolved/closed count toward none of the three.
        self._make(S.IN_PROGRESS, SS.DEVELOPMENT, dev=self.dev)
        self._make(S.IN_PROGRESS, SS.RETURNED, dev=self.dev)
        self._make(S.AWAITING_CLIENT, dev=self.dev)
        self._make(S.UAT, dev=self.dev)
        self._make(S.RESOLVED, dev=self.dev)
        self._make(S.CLOSED, dev=self.dev)

        d = self._dev(self.client.get(self.url), "dev_wl")
        self.assertEqual(d.wl_active, 3)
        self.assertEqual(d.wl_in_dev, 2)
        self.assertEqual(d.wl_in_uat, 1)

    def test_tester_workload_counts(self):
        # in_testing = in_progress·testing; queued = in_progress·{returned,ready_for_uat};
        # active = in_progress·{testing,returned,ready_for_uat} (its own filtered Count).
        self._make(S.IN_PROGRESS, SS.TESTING, tester=self.tester)
        self._make(S.IN_PROGRESS, SS.RETURNED, tester=self.tester)
        self._make(S.IN_PROGRESS, SS.READY_FOR_UAT, tester=self.tester)
        self._make(S.UAT, tester=self.tester)  # counts toward none

        t = self._tester(self.client.get(self.url), "tester_wl")
        self.assertEqual(t.wl_in_testing, 1)
        self.assertEqual(t.wl_queued, 2)
        self.assertEqual(t.wl_active, 3)

    def test_developer_workload_isolation(self):
        # Another dev's tickets must not count toward this one (both directions).
        self._make(S.IN_PROGRESS, SS.DEVELOPMENT, dev=self.dev)
        self._make(S.IN_PROGRESS, SS.DEVELOPMENT, dev=self.dev2)
        self._make(S.IN_PROGRESS, SS.DEVELOPMENT, dev=self.dev2)

        resp = self.client.get(self.url)
        d1 = self._dev(resp, "dev_wl")
        d2 = self._dev(resp, "dev_wl2")
        self.assertEqual((d1.wl_active, d1.wl_in_dev), (1, 1))
        self.assertEqual((d2.wl_active, d2.wl_in_dev), (2, 2))

    def test_tester_workload_isolation(self):
        self._make(S.IN_PROGRESS, SS.TESTING, tester=self.tester)
        self._make(S.IN_PROGRESS, SS.TESTING, tester=self.tester2)
        self._make(S.IN_PROGRESS, SS.TESTING, tester=self.tester2)

        resp = self.client.get(self.url)
        t1 = self._tester(resp, "tester_wl")
        t2 = self._tester(resp, "tester_wl2")
        self.assertEqual((t1.wl_in_testing, t1.wl_active), (1, 1))
        self.assertEqual((t2.wl_in_testing, t2.wl_active), (2, 2))

    def test_assign_dropdown_renders_workload_data_attr(self):
        # data-in-dev is dev-only; with one dev at in_dev=1 the attr renders once.
        self._make(S.IN_PROGRESS, SS.DEVELOPMENT, dev=self.dev)
        resp = self.client.get(self.url)
        self.assertContains(resp, 'data-in-dev="1"')


class AdminActionTierTests(TestCase):
    """Issues 1+4 + browser-fix redesign: the detail-modal Actions section keeps
    the forward action as a prominent Primary card, with every other action as a
    collapsed <details> disclosure (destructive ones red + last, NO "Danger"
    heading). Structural guards only (wrapper class + action presence) — the
    expand-on-click behavior is browser-verified. Exhaustive per-state action
    availability is covered by the existing detail tests.
    """

    def setUp(self):
        self.admin = User.objects.create_user("admin_at", role="admin")
        self.requester = User.objects.create_user("client_at", role="client")
        self.developer = User.objects.create_user("dev_at", role="developer")
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="A ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def _detail(self, t):
        return self.client.get(reverse("admin_ticket_detail", args=[t.pk]))

    def test_new_has_primary_assign_and_destructive_reject(self):
        resp = self._detail(self._make(S.NEW))
        self.assertContains(resp, "tw-action-card--primary")
        self.assertContains(resp, 'name="action" value="assign"')
        # Reject is a destructive disclosure — no old danger tier, no headings.
        self.assertContains(resp, "tw-disclosure--danger")
        self.assertContains(resp, 'name="action" value="reject"')
        self.assertNotContains(resp, "tw-action-tier--danger")
        self.assertNotContains(resp, ">Danger<")
        self.assertNotContains(resp, ">Manage<")

    def test_ready_for_uat_primary_send_to_uat_and_destructive_cancel(self):
        t = self._make(S.IN_PROGRESS, SS.READY_FOR_UAT, assigned_developer=self.developer)
        resp = self._detail(t)
        self.assertContains(resp, "tw-action-card--primary")
        self.assertContains(resp, 'name="action" value="send_to_uat"')
        self.assertContains(resp, "tw-disclosure--danger")
        self.assertContains(resp, 'name="action" value="cancel"')
        # 2+ manage disclosures (Request Info + Reassign) → "Manage" heading shows.
        self.assertContains(resp, ">Manage<")
        self.assertNotContains(resp, ">Danger<")

    def test_resolved_primary_close_and_reopen_disclosure(self):
        resp = self._detail(self._make(S.RESOLVED, assigned_developer=self.developer))
        self.assertContains(resp, "tw-action-card--primary")
        self.assertContains(resp, 'name="action" value="close"')
        self.assertContains(resp, "tw-disclosure")
        self.assertContains(resp, 'name="action" value="reopen"')
        # Single manage disclosure → no "Manage" heading.
        self.assertNotContains(resp, ">Manage<")
        self.assertNotContains(resp, ">Danger<")

    def test_cancelled_has_no_actions(self):
        resp = self._detail(self._make(S.CANCELLED))
        self.assertNotContains(resp, "tw-disclosure")
        self.assertNotContains(resp, "tw-action-card--primary")
        self.assertNotContains(resp, 'name="action"')

    def test_uat_recall_disclosure_only(self):
        # Single manage disclosure, no primary, no destructive, no headings.
        resp = self._detail(self._make(S.UAT, assigned_developer=self.developer))
        self.assertContains(resp, "tw-disclosure")
        self.assertContains(resp, 'name="action" value="request_changes"')
        self.assertNotContains(resp, "tw-disclosure--danger")
        self.assertNotContains(resp, "tw-action-card--primary")
        self.assertNotContains(resp, ">Manage<")
        self.assertNotContains(resp, ">Danger<")

    def test_manage_heading_only_for_multi_manage_states(self):
        # Renders for in_progress (Request Info + Reassign = 2 manage), absent for
        # the single-disclosure states.
        in_prog = self._detail(
            self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        )
        self.assertContains(in_prog, ">Manage<")
        for status in (S.RESOLVED, S.UAT, S.CLOSED):
            resp = self._detail(self._make(status, assigned_developer=self.developer))
            self.assertNotContains(resp, ">Manage<", msg_prefix=str(status))

    def test_partial_has_no_leaked_template_comment(self):
        # A multi-line {# #} leaks as text (Django comments are single-line); the
        # text contained "<details>" which the browser parsed as empty UA markers.
        # No rendered partial may contain a literal "{#".
        new = self._detail(self._make(S.NEW))
        self.assertNotContains(new, "{#")
        in_prog = self._detail(
            self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        )
        self.assertNotContains(in_prog, "{#")

    def test_disclosure_summaries_render_action_labels(self):
        # Each <summary> must carry its action-name label (an empty summary that
        # falls back to the UA "Details" marker would fail these).
        new = self._detail(self._make(S.NEW))
        self.assertContains(new, 'tw-disclosure__label">Reject Ticket</span>')
        in_prog = self._detail(
            self._make(S.IN_PROGRESS, SS.DEVELOPMENT, assigned_developer=self.developer)
        )
        self.assertContains(in_prog, 'tw-disclosure__label">Request Info</span>')
        self.assertContains(in_prog, 'tw-disclosure__label">Reassign</span>')
        self.assertContains(in_prog, 'tw-disclosure__label">Cancel Ticket</span>')


class AdminTopbarIdentityTests(TestCase):
    """Sweep S3: the admin topbar binds request.user, not the dummy."""

    def setUp(self):
        self.url = reverse("admin_dashboard")
        self.admin = User.objects.create_user(
            "demo_admin",
            email="demo.admin@tweedle.local",
            password="pw",
            role="admin",
            first_name="Demo",
            last_name="Admin",
        )

    def test_topbar_shows_real_user_identity(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        # Name, email, and slice(:2)-upper initials from request.user.
        self.assertContains(resp, "Demo Admin")
        self.assertContains(resp, "demo.admin@tweedle.local")
        self.assertContains(resp, ">DE<")  # "Demo Admin"[:2].upper()

    def test_topbar_dummy_identity_removed(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertNotContains(resp, "Jinoy Jose")
        self.assertNotContains(resp, "jinoy@tweedle.io")
        self.assertNotContains(resp, "CURRENT_USER")


class AdminNotificationBellTests(TestCase):
    """Sweep S4: the bell shows real notifications for request.user (read-only)."""

    def setUp(self):
        self.url = reverse("admin_dashboard")
        self.admin = User.objects.create_user(
            "admin_n", email="admin_n@tweedle.local", password="pw", role="admin"
        )
        self.other_admin = User.objects.create_user(
            "admin_n2", email="admin_n2@tweedle.local", password="pw", role="admin"
        )
        self.requester = User.objects.create_user(
            "client_n", email="client_n@tweedle.local", password="pw", role="client"
        )
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.ticket = Ticket.objects.create(
            subject="Bell ticket",
            requester=self.requester,
            client=self.org,
            status=S.NEW,
        )

    def _notif(self, recipient, message, is_read=False):
        return Notification.objects.create(
            recipient=recipient,
            ticket=self.ticket,
            action="assign",
            message=message,
            is_read=is_read,
        )

    def test_bell_shows_unread_count_and_notifications(self):
        self._notif(self.admin, "First bell message")
        self._notif(self.admin, "Second bell message")
        self._notif(self.admin, "Already read message", is_read=True)
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["unread_notification_count"], 2)
        self.assertContains(resp, "First bell message")
        self.assertContains(resp, "Second bell message")
        self.assertContains(resp, "Already read message")
        # The unread badge renders the real count.
        self.assertContains(resp, 'id="notifCount">2<')
        # Each item links to its ticket via the existing openTicket event.
        self.assertContains(resp, "tweedle:openTicket")
        self.assertContains(resp, self.ticket.reference)

    def test_bell_empty_state_when_none(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["unread_notification_count"], 0)
        self.assertEqual(list(resp.context["recent_notifications"]), [])
        self.assertContains(resp, "No notifications yet.")
        # No badge element when there are zero unread.
        self.assertNotContains(resp, 'id="notifCount"')

    def test_bell_excludes_other_users_notifications(self):
        self._notif(self.other_admin, "Not your notification")
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["unread_notification_count"], 0)
        self.assertNotContains(resp, "Not your notification")

    def test_bell_dummy_notifications_removed(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        # The hardcoded "8" badge and the four dummy notifications are gone.
        self.assertNotContains(resp, 'id="notifCount">8<')
        self.assertNotContains(resp, "Wallet Option Agents")
        self.assertNotContains(resp, "Recon issue has passed")
        self.assertNotContains(resp, "Payment Gateway Integration")
        self.assertNotContains(resp, "Authentication Flow Fix")

    def test_mark_all_read_is_a_real_server_form(self):
        # Phase 4.20: the cosmetic DOM-only button (id="markAllReadBtn") is gone;
        # the bell now exposes a REAL mark-all-read POST form when there are unread.
        self._notif(self.admin, "A message")
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertNotContains(resp, 'id="markAllReadBtn"')
        self.assertContains(resp, reverse("notifications_mark_all_read"))
        self.assertContains(resp, "Mark all read")


class AdminClientsPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "admin_c", email="admin_c@tweedle.local", password="pw", role="admin"
        )
        self.outsider = User.objects.create_user(
            "client_c", email="client_c@tweedle.local", password="pw", role="client"
        )
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.list_url = reverse("admin_clients")
        self.onboard_url = reverse("admin_onboard_client")

    # ── Access ───────────────────────────────────────────────────────────────

    def test_list_requires_admin(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_list_shows_clients(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Acme Corp")
        self.assertContains(resp, "ACME")

    def test_active_ticket_count_annotated(self):
        # One open + one closed ticket → active count should be 1.
        requester = self.outsider
        requester.client = self.org
        requester.save()
        Ticket.objects.create(
            subject="open", description="d" * 20, requester=requester,
            client=self.org, status=S.NEW,
        )
        Ticket.objects.create(
            subject="done", description="d" * 20, requester=requester,
            client=self.org, status=S.CLOSED,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(self.list_url)
        client_row = [c for c in resp.context["clients"] if c.pk == self.org.pk][0]
        self.assertEqual(client_row.active_tickets, 1)

    # ── Onboard ──────────────────────────────────────────────────────────────

    def _payload(self, **extra):
        data = {
            "name": "Globex Inc",
            "code": "GLBX",
            "country": "India",
            "contact_name": "Jane Doe",
            "contact_email": "jane@globex.test",
            "status": "active",
        }
        data.update(extra)
        return data

    def test_onboard_creates_client(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.onboard_url, self._payload())
        self.assertRedirects(resp, self.list_url)
        created = Client.objects.get(code="GLBX")
        self.assertEqual(created.name, "Globex Inc")
        self.assertEqual(created.contact_email, "jane@globex.test")
        self.assertEqual(created.status, "active")

    def test_onboard_uppercases_code(self):
        self.client.force_login(self.admin)
        self.client.post(self.onboard_url, self._payload(code="glbx"))
        self.assertTrue(Client.objects.filter(code="GLBX").exists())

    def test_onboard_missing_required_field_reopens_modal(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.onboard_url, self._payload(name=""))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Client.objects.filter(code="GLBX").exists())
        self.assertTrue(resp.context["open_onboard_modal"])

    def test_onboard_duplicate_code_rejected(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.onboard_url, self._payload(code="ACME"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Client.objects.filter(code="ACME").count(), 1)

    def test_onboard_requires_admin(self):
        self.client.force_login(self.outsider)
        resp = self.client.post(self.onboard_url, self._payload())
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Client.objects.filter(code="GLBX").exists())

    def test_onboard_get_not_allowed(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.onboard_url).status_code, 405)


class AdminTeamPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "admin_tm", email="admin_tm@tweedle.local", password="pw", role="admin"
        )
        self.outsider = User.objects.create_user(
            "client_tm", email="client_tm@tweedle.local", password="pw", role="client"
        )
        self.dev = User.objects.create_user(
            "dev_one", email="dev_one@tweedle.local", password="pw", role="developer"
        )
        self.tester = User.objects.create_user(
            "test_one", email="test_one@tweedle.local", password="pw", role="tester"
        )
        self.list_url = reverse("admin_team")
        self.add_url = reverse("admin_add_team_member")

    # ── Access / list ────────────────────────────────────────────────────────

    def test_list_requires_admin(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_list_shows_only_dev_and_tester(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        usernames = [m.username for m in resp.context["team_members"]]
        self.assertIn("dev_one", usernames)
        self.assertIn("test_one", usernames)
        self.assertNotIn("admin_tm", usernames)
        self.assertNotIn("client_tm", usernames)

    def test_workload_counts_active_assigned_tickets(self):
        org = Client.objects.create(name="Acme", code="ACME")
        requester = self.outsider
        requester.client = org
        requester.save()
        Ticket.objects.create(
            subject="a", description="d" * 20, requester=requester, client=org,
            status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT, assigned_developer=self.dev,
        )
        Ticket.objects.create(
            subject="b", description="d" * 20, requester=requester, client=org,
            status=S.CLOSED, assigned_developer=self.dev,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(self.list_url)
        dev_row = [m for m in resp.context["team_members"] if m.pk == self.dev.pk][0]
        self.assertEqual(dev_row.wl_dev + dev_row.wl_test, 1)

    # ── Add member ───────────────────────────────────────────────────────────

    def _payload(self, **extra):
        data = {
            "full_name": "Arjun Menon",
            "email": "arjun@tweedle.test",
            "role": "developer",
            "password": "TempPass!2026",
            "is_active": "on",
        }
        data.update(extra)
        return data

    def test_add_member_creates_active_user(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.add_url, self._payload())
        self.assertRedirects(resp, self.list_url)
        member = User.objects.get(email="arjun@tweedle.test")
        self.assertEqual(member.role, "developer")
        self.assertEqual(member.first_name, "Arjun")
        self.assertEqual(member.last_name, "Menon")
        self.assertTrue(member.is_active)
        self.assertEqual(member.username, "arjun_m")
        # Password is hashed and usable.
        self.assertTrue(member.check_password("TempPass!2026"))

    def test_add_member_inactive_when_unchecked(self):
        self.client.force_login(self.admin)
        payload = self._payload()
        payload.pop("is_active")  # checkbox unchecked
        self.client.post(self.add_url, payload)
        member = User.objects.get(email="arjun@tweedle.test")
        self.assertFalse(member.is_active)

    def test_add_member_unique_username(self):
        User.objects.create_user("arjun_m", email="other@x.test", password="pw", role="tester")
        self.client.force_login(self.admin)
        self.client.post(self.add_url, self._payload())
        member = User.objects.get(email="arjun@tweedle.test")
        self.assertEqual(member.username, "arjun_m2")

    def test_add_member_duplicate_email_rejected(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.add_url, self._payload(email="dev_one@tweedle.local"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["open_member_modal"])

    def test_add_member_short_password_rejected(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.add_url, self._payload(password="short"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email="arjun@tweedle.test").exists())

    def test_add_member_requires_admin(self):
        self.client.force_login(self.outsider)
        resp = self.client.post(self.add_url, self._payload())
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(User.objects.filter(email="arjun@tweedle.test").exists())

    # ── Enable / disable ─────────────────────────────────────────────────────

    def test_toggle_disables_then_enables(self):
        self.client.force_login(self.admin)
        url = reverse("admin_toggle_team_member", args=[self.dev.pk])
        self.client.post(url)
        self.dev.refresh_from_db()
        self.assertFalse(self.dev.is_active)
        self.client.post(url)
        self.dev.refresh_from_db()
        self.assertTrue(self.dev.is_active)

    def test_toggle_rejects_non_team_user(self):
        self.client.force_login(self.admin)
        url = reverse("admin_toggle_team_member", args=[self.outsider.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_toggle_requires_admin(self):
        self.client.force_login(self.outsider)
        url = reverse("admin_toggle_team_member", args=[self.dev.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
