"""Tests for the shared role-aware ticket-label matrix (TARGET §6).

Two layers:
  * matrix-level — assert every visible §6 cell, for ALL FIVE roles, resolves to
    the exact (label, css, title), and that N/A cells are absent;
  * view/render — assert the (now-migrated) CLIENT dashboard + detail render the
    §6 client labels for representative tickets (and the old internal strings are
    gone), including the uat + subuser_confirmed variant and the :336 prose.

Only the client portal is wired this step, but the whole matrix is encoded and
tested so the remaining four portals migrate against a fully-covered table.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.labels import CONFIRMED, TICKET_LABELS, resolve_ticket_label
from tickets.models import Ticket

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


# Expected §6 columns, transcribed verbatim. Key: (status, sub_status|None|CONFIRMED).
EXPECTED = {
    "admin": {
        (S.NEW, None): "New",
        (S.IN_PROGRESS, SS.DEVELOPMENT): "Development",
        (S.IN_PROGRESS, SS.TESTING): "Testing",
        (S.IN_PROGRESS, SS.RETURNED): "Returned from QA",
        (S.IN_PROGRESS, SS.READY_FOR_UAT): "Ready for UAT",
        (S.AWAITING_CLIENT, None): "Awaiting Client",
        (S.UAT, None): "UAT Approval",
        (S.UAT, CONFIRMED): "UAT — sub-user confirmed, awaiting client approval",
        (S.RESOLVED, None): "Resolved",
        (S.CLOSED, None): "Closed",
        (S.REJECTED, None): "Rejected",
        (S.CANCELLED, None): "Cancelled",
    },
    "client": {
        (S.NEW, None): "New — Received",
        (S.IN_PROGRESS, SS.DEVELOPMENT): "In Progress",
        (S.IN_PROGRESS, SS.TESTING): "In Progress",
        (S.IN_PROGRESS, SS.RETURNED): "In Progress",
        (S.IN_PROGRESS, SS.READY_FOR_UAT): "In Progress",
        (S.AWAITING_CLIENT, None): "Your Input Needed",
        (S.UAT, None): "Ready for Your Review",
        (S.UAT, CONFIRMED): "Ready for Your Review (sub-user confirmed)",
        (S.RESOLVED, None): "Awaiting Closure",
        (S.CLOSED, None): "Completed",
        (S.REJECTED, None): "Not Accepted",
        (S.CANCELLED, None): "Cancelled",
    },
    "developer": {
        (S.IN_PROGRESS, SS.DEVELOPMENT): "Development",
        (S.IN_PROGRESS, SS.TESTING): "In Testing",
        (S.IN_PROGRESS, SS.RETURNED): "Returned from QA",
        (S.IN_PROGRESS, SS.READY_FOR_UAT): "Ready for UAT",
        (S.AWAITING_CLIENT, None): "Paused — Awaiting Client",
        (S.UAT, None): "In Client UAT",
        (S.UAT, CONFIRMED): "In Client UAT",
        (S.RESOLVED, None): "Resolved",
        (S.CLOSED, None): "Closed",
        (S.CANCELLED, None): "Cancelled",
    },
    "tester": {
        (S.IN_PROGRESS, SS.TESTING): "Testing",
        (S.IN_PROGRESS, SS.RETURNED): "Failed",
        (S.IN_PROGRESS, SS.READY_FOR_UAT): "Passed",
    },
    "subuser": {
        (S.NEW, None): "New — Received",
        (S.IN_PROGRESS, SS.DEVELOPMENT): "In Progress",
        (S.IN_PROGRESS, SS.TESTING): "In Progress",
        (S.IN_PROGRESS, SS.RETURNED): "In Progress",
        (S.IN_PROGRESS, SS.READY_FOR_UAT): "In Progress",
        (S.AWAITING_CLIENT, None): "Your Input Needed",
        (S.UAT, None): "Please Verify",
        (S.UAT, CONFIRMED): "Confirmed — Awaiting Approval",
        (S.RESOLVED, None): "Awaiting Closure",
        (S.CLOSED, None): "Completed",
        (S.REJECTED, None): "Not Accepted",
        (S.CANCELLED, None): "Cancelled",
    },
}

# Cells that are N/A for a role per §6 — must be absent from the matrix and must
# fall through to the supplied fallback.
NA_CELLS = {
    "developer": [(S.NEW, None), (S.REJECTED, None)],
    "tester": [
        (S.NEW, None),
        (S.IN_PROGRESS, SS.DEVELOPMENT),
        (S.AWAITING_CLIENT, None),
        (S.UAT, None),
        (S.UAT, CONFIRMED),
        (S.RESOLVED, None),
        (S.CLOSED, None),
        (S.REJECTED, None),
        (S.CANCELLED, None),
    ],
}

_SENTINEL_FALLBACK = ("__fb_label__", "__fb_css__", "__fb_title__")


class MatrixLabelTests(TestCase):
    """Every §6 cell for every role resolves to the exact expected label."""

    def _resolve(self, role, status, sub):
        confirmed = sub is CONFIRMED
        # CONFIRMED rows describe a uat ticket; pass the real sub_status (None).
        real_sub = None if sub is CONFIRMED else sub
        return resolve_ticket_label(
            role, status, real_sub, subuser_confirmed=confirmed,
            fallback=_SENTINEL_FALLBACK,
        )

    def test_client_column_matches_target_six(self):
        for (status, sub), expected in EXPECTED["client"].items():
            label, _css, _title = self._resolve("client", status, sub)
            self.assertEqual(
                label, expected,
                f"client ({status}, {sub}) -> {label!r}, expected {expected!r}",
            )

    def test_admin_column_matches_target_six(self):
        for (status, sub), expected in EXPECTED["admin"].items():
            label, _css, _title = self._resolve("admin", status, sub)
            self.assertEqual(label, expected, f"admin ({status}, {sub})")

    def test_developer_column_matches_target_six(self):
        for (status, sub), expected in EXPECTED["developer"].items():
            label, _css, _title = self._resolve("developer", status, sub)
            self.assertEqual(label, expected, f"developer ({status}, {sub})")

    def test_tester_column_matches_target_six(self):
        for (status, sub), expected in EXPECTED["tester"].items():
            label, _css, _title = self._resolve("tester", status, sub)
            self.assertEqual(label, expected, f"tester ({status}, {sub})")

    def test_subuser_column_matches_target_six(self):
        for (status, sub), expected in EXPECTED["subuser"].items():
            label, _css, _title = self._resolve("subuser", status, sub)
            self.assertEqual(label, expected, f"subuser ({status}, {sub})")

    def test_na_cells_absent_and_fall_back(self):
        for role, cells in NA_CELLS.items():
            for (status, sub) in cells:
                self.assertNotIn(
                    (role, status, sub if sub is CONFIRMED else sub),
                    TICKET_LABELS,
                    f"{role} ({status}, {sub}) should be N/A (absent)",
                )
                self.assertEqual(
                    self._resolve(role, status, sub), _SENTINEL_FALLBACK,
                    f"{role} ({status}, {sub}) should fall back",
                )

    def test_css_and_title_preserved_for_representative_cells(self):
        # css-modifier + title contract is intact (drop-in for the legacy dicts).
        self.assertEqual(
            resolve_ticket_label("admin", S.IN_PROGRESS, SS.RETURNED),
            ("Returned from QA", "returned", "Returned from Testing"),
        )
        self.assertEqual(
            resolve_ticket_label("client", S.UAT, None, subuser_confirmed=True),
            ("Ready for Your Review (sub-user confirmed)", "uat",
             "Sub-user confirmed — awaiting your approval"),
        )


class ResolverBehaviourTests(TestCase):
    def test_sub_status_ignored_unless_in_progress(self):
        # A stray sub_status on a non-in_progress ticket must be collapsed.
        self.assertEqual(
            resolve_ticket_label("client", S.RESOLVED, SS.DEVELOPMENT)[0],
            "Awaiting Closure",
        )

    def test_uat_confirmed_picks_confirmed_variant(self):
        self.assertEqual(
            resolve_ticket_label("client", S.UAT, None, subuser_confirmed=True)[0],
            "Ready for Your Review (sub-user confirmed)",
        )
        self.assertEqual(
            resolve_ticket_label("client", S.UAT, None, subuser_confirmed=False)[0],
            "Ready for Your Review",
        )

    def test_developer_confirmed_uat_equals_plain_uat(self):
        self.assertEqual(
            resolve_ticket_label("developer", S.UAT, None, subuser_confirmed=True)[0],
            "In Client UAT",
        )

    def test_unknown_key_returns_fallback(self):
        self.assertEqual(
            resolve_ticket_label("tester", S.UAT, None, fallback=_SENTINEL_FALLBACK),
            _SENTINEL_FALLBACK,
        )

    def test_unknown_key_without_fallback_derives_default(self):
        self.assertEqual(
            resolve_ticket_label("tester", S.CLOSED, None),
            (S.CLOSED, S.CLOSED, ""),
        )


class ClientRenderTests(TestCase):
    """The migrated client dashboard + detail render the §6 client labels."""

    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.client_user = User.objects.create_user(
            "client_main", email="cm@test.local", password="pw",
            role="client", client=self.org,
        )
        self.client.force_login(self.client_user)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="Render test ticket",
            description="Body.",
            requester=self.client_user,
            client=self.org,
            status=status,
            sub_status=sub_status,
            **kw,
        )

    # ── Dashboard ──────────────────────────────────────────────────────────
    def test_dashboard_uat_badge_uses_target_label(self):
        self._make(S.UAT)
        resp = self.client.get(reverse("client_dashboard"))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--uat">Ready for Your Review</span>',
            html=False,
        )
        self.assertNotContains(resp, ">UAT Approval</span>")

    def test_dashboard_uat_confirmed_badge_variant(self):
        self._make(S.UAT, subuser_confirmed=True)
        resp = self.client.get(reverse("client_dashboard"))
        self.assertContains(resp, "Ready for Your Review (sub-user confirmed)")

    def test_dashboard_resolved_and_closed_and_rejected_labels(self):
        self._make(S.RESOLVED)
        self._make(S.CLOSED)
        self._make(S.REJECTED)
        resp = self.client.get(reverse("client_dashboard"))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--resolved">Awaiting Closure</span>',
        )
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--closed">Completed</span>',
        )
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--rejected">Not Accepted</span>',
        )
        # Old internal badge labels must be gone (these strings appear nowhere
        # else on the client dashboard).
        self.assertNotContains(resp, ">UAT Approval</span>")
        self.assertNotContains(resp, ">Resolved</span>")

    def test_dashboard_new_badge_label(self):
        self._make(S.NEW)
        resp = self.client.get(reverse("client_dashboard"))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--new">New — Received</span>',
        )

    # ── Detail ─────────────────────────────────────────────────────────────
    def test_detail_uat_renders_target_label(self):
        t = self._make(S.UAT)
        resp = self.client.get(reverse("client_ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Ready for Your Review")
        self.assertNotContains(resp, ">UAT Approval</span>")

    def test_detail_uat_confirmed_renders_variant(self):
        t = self._make(S.UAT, subuser_confirmed=True)
        resp = self.client.get(reverse("client_ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Ready for Your Review (sub-user confirmed)")

    def test_detail_closed_prose_uses_client_label_not_raw_status(self):
        # The :336 chat-notice sentence reads in client-facing language.
        t = self._make(S.CLOSED)
        resp = self.client.get(reverse("client_ticket_detail", args=[t.pk]))
        self.assertContains(resp, "This ticket is completed.")
        self.assertNotContains(resp, "This ticket is closed.")


class DeveloperRenderTests(TestCase):
    """The migrated developer dashboard + detail render the §6 developer labels."""

    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.dev = User.objects.create_user(
            "dev_main", email="dev@test.local", password="pw", role="developer"
        )
        self.requester = User.objects.create_user(
            "req", email="req@test.local", password="pw", role="client", client=self.org
        )
        self.client.force_login(self.dev)

    def _make(self, status, sub_status=None, **kw):
        kw.setdefault("assigned_developer", self.dev)
        return Ticket.objects.create(
            subject="Dev render ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def test_dashboard_awaiting_client_uses_paused_label(self):
        self._make(S.AWAITING_CLIENT)
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--forwarded">Paused — Awaiting Client</span>',
        )
        # The old (pre-matrix) badge fragment must be gone (matched in full, since
        # "Awaiting Client" is a substring of the new label).
        self.assertNotContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--forwarded">Awaiting Client</span>',
        )

    def test_dashboard_development_and_uat_labels(self):
        self._make(S.IN_PROGRESS, SS.DEVELOPMENT)
        self._make(S.UAT)
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertContains(resp, ">Development</span>")
        self.assertContains(resp, ">In Client UAT</span>")

    def test_detail_awaiting_client_paused_badge(self):
        t = self._make(S.AWAITING_CLIENT)
        resp = self.client.get(reverse("dev:ticket_detail", args=[t.pk]))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--forwarded">Paused — Awaiting Client</span>',
        )
        self.assertNotContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--forwarded">Awaiting Client</span>',
        )


class TesterRenderTests(TestCase):
    """The migrated tester dashboard + detail render the §6 tester labels."""

    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.tester = User.objects.create_user(
            "qa_main", email="qam@test.local", password="pw", role="tester"
        )
        self.dev = User.objects.create_user(
            "dev2", email="dev2@test.local", password="pw", role="developer"
        )
        self.requester = User.objects.create_user(
            "req2", email="req2@test.local", password="pw", role="client", client=self.org
        )
        self.client.force_login(self.tester)

    def _make(self, sub_status, **kw):
        return Ticket.objects.create(
            subject="QA render ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=S.IN_PROGRESS, sub_status=sub_status,
            assigned_developer=self.dev, assigned_tester=self.tester, **kw,
        )

    def test_dashboard_three_states(self):
        self._make(SS.TESTING)
        self._make(SS.RETURNED)
        self._make(SS.READY_FOR_UAT)
        resp = self.client.get(reverse("tester:dashboard"))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--testing">Testing</span>',
        )
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--returned" title="Returned to Developer">Failed</span>',
        )
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--testing-passed" title="Testing Passed — Ready for UAT">Passed</span>',
        )

    def test_detail_testing_badge(self):
        t = self._make(SS.TESTING)
        resp = self.client.get(reverse("tester:ticket_detail", args=[t.pk]))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--testing">Testing</span>',
        )


class SubuserRenderTests(TestCase):
    """The migrated sub-user dashboard + detail render the §6 sub-user labels."""

    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.subuser = User.objects.create_user(
            "sub_main", email="sub@test.local", password="pw",
            role="subuser", client=self.org,
        )
        self.client.force_login(self.subuser)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="Sub render ticket", description="Body.",
            requester=self.subuser, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    def test_dashboard_labels(self):
        self._make(S.NEW)
        self._make(S.UAT)
        self._make(S.RESOLVED)
        self._make(S.CLOSED)
        self._make(S.REJECTED)
        resp = self.client.get(reverse("subuser:dashboard"))
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--new">New — Received</span>',
        )
        self.assertContains(resp, "Please Verify")
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--resolved">Awaiting Closure</span>',
        )
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--closed">Completed</span>',
        )
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--rejected">Not Accepted</span>',
        )

    def test_dashboard_uat_confirmed_variant(self):
        self._make(S.UAT, subuser_confirmed=True)
        resp = self.client.get(reverse("subuser:dashboard"))
        self.assertContains(resp, "Confirmed — Awaiting Approval")
        self.assertNotContains(resp, ">Please Verify<")

    def test_detail_uat_confirmed_variant(self):
        t = self._make(S.UAT, subuser_confirmed=True)
        resp = self.client.get(reverse("subuser:ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Confirmed — Awaiting Approval")


class AdminRenderTests(TestCase):
    """The migrated admin dashboard + detail partial render the §6 admin labels."""

    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.admin = User.objects.create_user(
            "admin_main", email="admin@test.local", password="pw", role="admin"
        )
        self.requester = User.objects.create_user(
            "req_a", email="reqa@test.local", password="pw", role="client", client=self.org
        )
        self.client.force_login(self.admin)

    def _make(self, status, sub_status=None, **kw):
        return Ticket.objects.create(
            subject="Admin render ticket", description="Body.",
            requester=self.requester, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )

    # ── Detail partial: every §6 admin cell ─────────────────────────────────
    def test_detail_partial_renders_each_admin_cell(self):
        cases = [
            (S.NEW, None, False,
             '<span class="tw-status-badge tw-status-badge--new">New</span>'),
            (S.IN_PROGRESS, SS.DEVELOPMENT, False,
             '<span class="tw-status-badge tw-status-badge--development">Development</span>'),
            (S.IN_PROGRESS, SS.TESTING, False,
             '<span class="tw-status-badge tw-status-badge--testing">Testing</span>'),
            (S.IN_PROGRESS, SS.RETURNED, False,
             '<span class="tw-status-badge tw-status-badge--returned" title="Returned from Testing">Returned from QA</span>'),
            (S.IN_PROGRESS, SS.READY_FOR_UAT, False,
             '<span class="tw-status-badge tw-status-badge--testing-passed" title="Testing Passed — Ready for UAT">Ready for UAT</span>'),
            (S.AWAITING_CLIENT, None, False,
             '<span class="tw-status-badge tw-status-badge--forwarded">Awaiting Client</span>'),
            (S.UAT, None, False,
             '<span class="tw-status-badge tw-status-badge--uat">UAT Approval</span>'),
            (S.UAT, None, True,
             '<span class="tw-status-badge tw-status-badge--uat" title="Sub-user confirmed — awaiting client approval">UAT — sub-user confirmed, awaiting client approval</span>'),
            (S.RESOLVED, None, False,
             '<span class="tw-status-badge tw-status-badge--resolved">Resolved</span>'),
            (S.CLOSED, None, False,
             '<span class="tw-status-badge tw-status-badge--closed">Closed</span>'),
            (S.REJECTED, None, False,
             '<span class="tw-status-badge tw-status-badge--rejected">Rejected</span>'),
            (S.CANCELLED, None, False,
             '<span class="tw-status-badge tw-status-badge--rejected">Cancelled</span>'),
        ]
        for status, sub, confirmed, fragment in cases:
            t = self._make(status, sub, subuser_confirmed=confirmed)
            resp = self.client.get(reverse("admin_ticket_detail", args=[t.pk]))
            self.assertContains(resp, fragment, msg_prefix=f"{status}/{sub}/confirmed={confirmed}")

    def test_detail_returned_has_no_short_label(self):
        t = self._make(S.IN_PROGRESS, SS.RETURNED)
        resp = self.client.get(reverse("admin_ticket_detail", args=[t.pk]))
        self.assertContains(resp, ">Returned from QA</span>")
        self.assertNotContains(resp, ">Returned</span>")

    # ── Dashboard tabs that render a badge ───────────────────────────────────
    def test_dashboard_tab_badges(self):
        self._make(S.NEW)
        self._make(S.IN_PROGRESS, SS.RETURNED)
        self._make(S.AWAITING_CLIENT)
        self._make(S.CLOSED)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertContains(
            resp, '<span class="tw-status-badge tw-status-badge--new">New</span>')
        # In-Progress Stage column shows the full §6 label, not the short one.
        self.assertContains(resp, ">Returned from QA</span>")
        self.assertNotContains(resp, ">Returned</span>")
        self.assertContains(
            resp,
            '<span class="tw-status-badge tw-status-badge--forwarded">Awaiting Client</span>')
        self.assertContains(
            resp, '<span class="tw-status-badge tw-status-badge--closed">Closed</span>')

    # ── Option A: search-feed row attributes are matrix-sourced ──────────────
    def test_search_rows_carry_matrix_status_attrs(self):
        # In-Progress (returned) row → sub-status-aware label + css.
        self._make(S.IN_PROGRESS, SS.RETURNED)
        # A uat row has no in-table badge, but search must still surface its §6 label.
        self._make(S.UAT)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertContains(resp, 'data-status-label="Returned from QA"')
        self.assertContains(resp, 'data-status-css="returned"')
        self.assertContains(resp, 'data-status-label="UAT Approval"')
