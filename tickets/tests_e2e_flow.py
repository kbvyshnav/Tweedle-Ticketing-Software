"""Cross-portal end-to-end lifecycle verification (Step 6).

Drives ONE ticket through the full lifecycle via the REAL portal transition
endpoints (not transition() directly), so the whole stack is exercised at every
stage: each portal's ALLOWED_ACTIONS whitelist + object-level ownership + the
guarded engine + the server-rendered §6 labels and action controls.

At each stage we assert:
  (i)   status / sub_status,
  (ii)  visibility — the ticket is in the right portals' dashboard querysets and
        absent where it shouldn't be,
  (iii) rendering — each relevant portal shows the §6 label for that role and the
        correct available action controls,
plus cheap notification spot-checks (TARGET §7).

Engine-level transition/guard correctness is covered in tickets/tests.py; this
module is about the cross-portal wiring as a whole.

KNOWN DIVERGENCES asserted/characterised here (captured, not fixed this step):
  * #2 — a primary client cannot approve/request_changes a SUB-USER-submitted
    ticket (engine ownership guard restricts these to the requester-or-admin);
    only admin can resolve such a ticket. See
    test_branch_subuser_confirm_then_admin_approve.
  * #3 — the client `awaiting_client` "Respond" button is a disabled placeholder
    (blocked on chat posting). See test_branch_request_info_resume.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from notifications.models import Notification
from tickets.models import Ticket

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus

SUBMIT_DATA = {
    "subject": "Export downloads an empty file",
    "description": "When I click Export on the Reports page the file is empty.",
    "category": "Bug",
    "priority": "high",
}


class E2EBase(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.admin = User.objects.create_user("admin_e2e", role="admin")
        self.client_user = User.objects.create_user(
            "client_e2e", role="client", client=self.org
        )
        self.subuser = User.objects.create_user(
            "subuser_e2e", role="subuser", client=self.org
        )
        self.developer = User.objects.create_user("dev_e2e", role="developer")
        self.tester = User.objects.create_user("tester_e2e", role="tester")

    # ── drivers (all go through the real portal endpoints) ───────────────
    def _submit(self, submitter, url_name):
        self.client.force_login(submitter)
        resp = self.client.post(reverse(url_name), SUBMIT_DATA)
        self.assertEqual(resp.status_code, 302, "submit should redirect on success")
        ticket = Ticket.objects.filter(requester=submitter).order_by("-created_at").first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.status, S.NEW)
        return ticket

    def _act(self, actor, url_name, ticket, expect_status=None, expect_sub=..., **data):
        """force_login `actor`, POST the transition endpoint, refresh the ticket."""
        self.client.force_login(actor)
        resp = self.client.post(reverse(url_name, args=[ticket.pk]), data)
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        if expect_status is not None:
            self.assertEqual(ticket.status, expect_status)
        if expect_sub is not ...:
            self.assertEqual(ticket.sub_status, expect_sub)
        return resp

    # ── readers ──────────────────────────────────────────────────────────
    def _dash(self, user, url_name):
        self.client.force_login(user)
        return self.client.get(reverse(url_name))

    def _detail(self, user, url_name, ticket):
        self.client.force_login(user)
        return self.client.get(reverse(url_name, args=[ticket.pk]))

    def _pks(self, resp, ctx_key):
        return [t.pk for t in resp.context[ctx_key]]

    def _notified(self, recipient, ticket, action):
        return Notification.objects.filter(
            recipient=recipient, ticket=ticket, action=action
        ).exists()

    # ── shared mid-lifecycle driver ──────────────────────────────────────
    def _drive_to_uat(self, submitter, submit_url, with_tester=True):
        ticket = self._submit(submitter, submit_url)
        assign = {"action": "assign", "developer": self.developer.pk}
        if with_tester:
            assign["tester"] = self.tester.pk
        self._act(self.admin, "ticket_transition", ticket,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT, **assign)
        if with_tester:
            self._act(self.developer, "dev:ticket_transition", ticket,
                      expect_sub=SS.TESTING, action="submit_for_testing")
            self._act(self.tester, "tester:ticket_transition", ticket,
                      expect_sub=SS.READY_FOR_UAT, action="pass")
        else:
            self._act(self.developer, "dev:ticket_transition", ticket,
                      expect_sub=SS.READY_FOR_UAT, action="mark_ready")
        self._act(self.admin, "ticket_transition", ticket,
                  expect_status=S.UAT, expect_sub=None, action="send_to_uat")
        return ticket


class HappyPathTests(E2EBase):
    def test_happy_path_submit_to_close(self):
        # ── Stage 1: client submits → new ────────────────────────────────
        t = self._submit(self.client_user, "client_submit_ticket")
        self.assertEqual(t.requester, self.client_user)
        self.assertEqual(t.client, self.org)
        # admin inbox "New"
        admin = self._dash(self.admin, "admin_dashboard")
        self.assertIn(t.pk, self._pks(admin, "inbox_tickets"))
        self.assertContains(
            admin, '<span class="tw-status-badge tw-status-badge--new">New</span>')
        # client "New — Received"
        cli = self._dash(self.client_user, "client_dashboard")
        self.assertIn(t.pk, self._pks(cli, "tickets"))
        self.assertContains(
            cli, '<span class="tw-status-badge tw-status-badge--new">New — Received</span>')
        # absent from subuser (requester≠subuser), dev, tester
        self.assertNotIn(t.pk, self._pks(self._dash(self.subuser, "subuser:dashboard"), "tickets"))
        self.assertNotIn(t.pk, self._pks(self._dash(self.developer, "dev:dashboard"), "assigned_tickets"))
        self.assertNotIn(t.pk, self._pks(self._dash(self.tester, "tester:dashboard"), "assigned_tickets"))

        # ── Stage 2: admin assign (dev + tester) → in_progress·development ─
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="assign", developer=self.developer.pk, tester=self.tester.pk)
        self.assertTrue(self._notified(self.developer, t, "assign"))
        self.assertTrue(self._notified(self.tester, t, "assign"))
        # admin "Development"
        admin = self._dash(self.admin, "admin_dashboard")
        self.assertIn(t.pk, self._pks(admin, "inprogress_tickets"))
        self.assertContains(admin, ">Development</span>")
        # client "In Progress"
        self.assertContains(self._dash(self.client_user, "client_dashboard"), ">In Progress</span>")
        # dev now visible → "Development" + Submit for Testing control
        dev = self._dash(self.developer, "dev:dashboard")
        self.assertIn(t.pk, self._pks(dev, "assigned_tickets"))
        self.assertContains(dev, ">Development</span>")
        self.assertContains(self._detail(self.developer, "dev:ticket_detail", t),
                            'value="submit_for_testing"')
        # tester still absent (development ∉ tester's visible sub-statuses)
        self.assertNotIn(t.pk, self._pks(self._dash(self.tester, "tester:dashboard"), "assigned_tickets"))

        # ── Stage 3: dev submit_for_testing → in_progress·testing ─────────
        self._act(self.developer, "dev:ticket_transition", t,
                  expect_sub=SS.TESTING, action="submit_for_testing")
        self.assertTrue(self._notified(self.tester, t, "submit_for_testing"))
        # tester now visible → "Testing" + Pass/Fail
        tdash = self._dash(self.tester, "tester:dashboard")
        self.assertIn(t.pk, self._pks(tdash, "assigned_tickets"))
        self.assertContains(
            tdash, '<span class="tw-status-badge tw-status-badge--testing">Testing</span>')
        tdetail = self._detail(self.tester, "tester:ticket_detail", t)
        self.assertContains(tdetail, 'value="pass"')
        self.assertContains(tdetail, 'value="fail"')
        # dev sees "In Testing"; admin "Testing"
        self.assertContains(self._dash(self.developer, "dev:dashboard"), ">In Testing</span>")
        self.assertContains(self._dash(self.admin, "admin_dashboard"), ">Testing</span>")

        # ── Stage 4: tester pass → in_progress·ready_for_uat ──────────────
        self._act(self.tester, "tester:ticket_transition", t,
                  expect_sub=SS.READY_FOR_UAT, action="pass")
        self.assertTrue(self._notified(self.admin, t, "pass"))
        # admin "Ready for UAT" + Send to Client UAT (dashboard inline)
        admin = self._dash(self.admin, "admin_dashboard")
        self.assertContains(admin, ">Ready for UAT</span>")
        self.assertContains(admin, 'value="send_to_uat"')
        # tester "Passed"; dev "Ready for UAT"
        self.assertContains(self._dash(self.tester, "tester:dashboard"), ">Passed</span>")
        self.assertContains(self._dash(self.developer, "dev:dashboard"), ">Ready for UAT</span>")

        # ── Stage 5: admin send_to_uat → uat ──────────────────────────────
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.UAT, expect_sub=None, action="send_to_uat")
        self.assertTrue(self._notified(self.client_user, t, "send_to_uat"))
        # client "Ready for Your Review" + Approve/Request Changes
        self.assertContains(self._dash(self.client_user, "client_dashboard"),
                            ">Ready for Your Review</span>")
        cdetail = self._detail(self.client_user, "client_ticket_detail", t)
        self.assertContains(cdetail, 'value="approve"')
        self.assertContains(cdetail, 'value="request_changes"')
        # admin "UAT Approval" + Recall. NOTE: the admin UAT *tab* has no Status
        # column (status is implied by the tab), so the badge renders in the
        # detail modal, not the dashboard.
        adetail = self._detail(self.admin, "admin_ticket_detail", t)
        self.assertContains(adetail, ">UAT Approval</span>")
        self.assertContains(adetail, 'value="request_changes"')
        self.assertContains(self._dash(self.developer, "dev:dashboard"), ">In Client UAT</span>")
        # tester now absent (status≠in_progress)
        self.assertNotIn(t.pk, self._pks(self._dash(self.tester, "tester:dashboard"), "assigned_tickets"))

        # ── Stage 6: client approve → resolved ────────────────────────────
        self._act(self.client_user, "client_ticket_transition", t,
                  expect_status=S.RESOLVED, expect_sub=None, action="approve")
        self.assertTrue(self._notified(self.admin, t, "approve"))
        self.assertTrue(self._notified(self.developer, t, "approve"))
        # client "Awaiting Closure" + Reopen; admin "Resolved" + Close/Reopen
        self.assertContains(self._dash(self.client_user, "client_dashboard"),
                            ">Awaiting Closure</span>")
        adetail = self._detail(self.admin, "admin_ticket_detail", t)
        self.assertContains(adetail, 'value="close"')
        self.assertContains(adetail, 'value="reopen"')
        self.assertIn(t.pk, self._pks(self._dash(self.admin, "admin_dashboard"), "resolved_tickets"))

        # ── Stage 7: admin close → closed ─────────────────────────────────
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.CLOSED, expect_sub=None, action="close")
        self.assertTrue(self._notified(self.client_user, t, "close"))
        # admin "Closed" + Reopen; client "Completed"
        self.assertIn(t.pk, self._pks(self._dash(self.admin, "admin_dashboard"), "closed_tickets"))
        self.assertContains(self._detail(self.admin, "admin_ticket_detail", t), 'value="reopen"')
        self.assertContains(self._dash(self.client_user, "client_dashboard"), ">Completed</span>")


class BranchTests(E2EBase):
    def test_branch_tester_fail_then_resubmit(self):
        t = self._submit(self.client_user, "client_submit_ticket")
        self._act(self.admin, "ticket_transition", t, action="assign",
                  developer=self.developer.pk, tester=self.tester.pk)
        self._act(self.developer, "dev:ticket_transition", t,
                  expect_sub=SS.TESTING, action="submit_for_testing")
        # tester fail → returned
        self._act(self.tester, "tester:ticket_transition", t,
                  expect_sub=SS.RETURNED, action="fail", failure_notes="Still empty on Chrome")
        self.assertTrue(self._notified(self.developer, t, "fail"))
        self.assertContains(self._dash(self.tester, "tester:dashboard"), ">Failed</span>")
        dev = self._dash(self.developer, "dev:dashboard")
        self.assertContains(dev, ">Returned from QA</span>")
        self.assertContains(self._detail(self.developer, "dev:ticket_detail", t),
                            'value="resubmit_for_testing"')
        # dev resubmit → testing
        self._act(self.developer, "dev:ticket_transition", t,
                  expect_sub=SS.TESTING, action="resubmit_for_testing")

    def test_branch_no_tester_mark_ready(self):
        t = self._submit(self.client_user, "client_submit_ticket")
        # assign dev only (no tester)
        self._act(self.admin, "ticket_transition", t,
                  expect_sub=SS.DEVELOPMENT, action="assign", developer=self.developer.pk)
        self.assertFalse(t.assigned_tester_id)
        # dev detail shows Mark Ready (not Submit for Testing)
        ddetail = self._detail(self.developer, "dev:ticket_detail", t)
        self.assertContains(ddetail, 'value="mark_ready"')
        self.assertNotContains(ddetail, 'value="submit_for_testing"')
        self._act(self.developer, "dev:ticket_transition", t,
                  expect_sub=SS.READY_FOR_UAT, action="mark_ready")
        self.assertTrue(self._notified(self.admin, t, "mark_ready"))
        # tester never sees it
        self.assertNotIn(t.pk, self._pks(self._dash(self.tester, "tester:dashboard"), "assigned_tickets"))

    def test_branch_uat_client_request_changes(self):
        t = self._drive_to_uat(self.client_user, "client_submit_ticket")
        # client (requester) request_changes → in_progress·development
        self._act(self.client_user, "client_ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="request_changes", feedback="Logout still broken")
        self.assertTrue(self._notified(self.developer, t, "request_changes"))
        self.assertContains(self._dash(self.developer, "dev:dashboard"), ">Development</span>")
        self.assertContains(self._detail(self.developer, "dev:ticket_detail", t),
                            'value="submit_for_testing"')

    def test_branch_uat_admin_recall(self):
        t = self._drive_to_uat(self.client_user, "client_submit_ticket")
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="request_changes", feedback="Recalling for a fix")
        self.assertContains(self._dash(self.developer, "dev:dashboard"), ">Development</span>")

    def test_branch_request_info_resume(self):
        t = self._submit(self.client_user, "client_submit_ticket")
        self._act(self.admin, "ticket_transition", t, action="assign",
                  developer=self.developer.pk, tester=self.tester.pk)
        # admin request_info → awaiting_client
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.AWAITING_CLIENT, expect_sub=None,
                  action="request_info", message="Which browser?")
        self.assertTrue(self._notified(self.client_user, t, "request_info"))
        # client "Your Input Needed"; dev "Paused — Awaiting Client"
        self.assertContains(self._dash(self.client_user, "client_dashboard"),
                            ">Your Input Needed</span>")
        self.assertContains(self._dash(self.developer, "dev:dashboard"),
                            ">Paused — Awaiting Client</span>")
        # KNOWN DIVERGENCE #3: the client "Respond" control is a disabled placeholder
        # (blocked on chat posting). Assert it renders disabled, NOT functional.
        cdetail = self._detail(self.client_user, "client_ticket_detail", t)
        self.assertContains(cdetail, "Respond")
        self.assertContains(cdetail, "disabled")
        # admin drives the resume → back in_progress (restores paused dev stage)
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT, action="resume")
        self.assertTrue(self._notified(self.developer, t, "resume"))

    def test_branch_reject_then_restore(self):
        t = self._submit(self.client_user, "client_submit_ticket")
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.REJECTED, expect_sub=None,
                  action="reject", reason="Out of scope")
        self.assertTrue(self._notified(self.client_user, t, "reject"))
        # admin Rejected tab + Restore; client "Not Accepted"
        self.assertIn(t.pk, self._pks(self._dash(self.admin, "admin_dashboard"), "rejected_tickets"))
        self.assertContains(self._detail(self.admin, "admin_ticket_detail", t), 'value="restore"')
        self.assertContains(self._dash(self.client_user, "client_dashboard"), ">Not Accepted</span>")
        # admin restore → new
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.NEW, expect_sub=None, action="restore")
        self.assertIn(t.pk, self._pks(self._dash(self.admin, "admin_dashboard"), "inbox_tickets"))

    def test_branch_reopen_from_resolved(self):
        t = self._drive_to_uat(self.client_user, "client_submit_ticket")
        self._act(self.client_user, "client_ticket_transition", t,
                  expect_status=S.RESOLVED, action="approve")
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="reopen", reason="Regression")
        self.assertEqual(t.assigned_developer, self.developer)  # re-routed to original dev

    def test_branch_reopen_from_closed(self):
        t = self._drive_to_uat(self.client_user, "client_submit_ticket")
        self._act(self.client_user, "client_ticket_transition", t,
                  expect_status=S.RESOLVED, action="approve")
        self._act(self.admin, "ticket_transition", t, expect_status=S.CLOSED, action="close")
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="reopen", reason="Came back")
        self.assertEqual(t.assigned_developer, self.developer)

    def test_branch_admin_cancel(self):
        t = self._submit(self.client_user, "client_submit_ticket")
        self._act(self.admin, "ticket_transition", t, action="assign",
                  developer=self.developer.pk, tester=self.tester.pk)
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.CANCELLED, expect_sub=None,
                  action="cancel", reason="Duplicate of GMEC…")
        self.assertTrue(self._notified(self.client_user, t, "cancel"))
        # admin Cancelled tab + "Cancelled" badge; client "Cancelled"; read-only detail
        admin = self._dash(self.admin, "admin_dashboard")
        self.assertIn(t.pk, self._pks(admin, "cancelled_tickets"))
        self.assertContains(
            admin, '<span class="tw-status-badge tw-status-badge--rejected">Cancelled</span>')
        self.assertContains(self._dash(self.client_user, "client_dashboard"), ">Cancelled</span>")
        self.assertNotContains(self._detail(self.admin, "admin_ticket_detail", t), 'name="action"')

    def test_branch_subuser_confirm_resolution_blocked(self):
        """Sub-user-submitted ticket: confirm works, but resolution is BLOCKED.

        KNOWN DIVERGENCE (escalates finding #2 — captured, NOT fixed this step;
        a fix decision is pending). TARGET §4/§6 say the client/admin hold final
        approval of a sub-user-submitted ticket. In the current build NEITHER can
        approve it through any portal:
          * client endpoint `approve` → engine ownership guard
            (`_require_requester_or_admin`) blocks the non-requester client;
          * admin endpoint has NO `approve` in ALLOWED_ACTIONS (approve was only
            ever wired into the client portal as the T7 action), so admin
            `approve` is rejected as an unsupported action;
          * the sub-user (the requester) lacks the `approve` role entirely.
        ⇒ a sub-user-submitted ticket is STUCK at `uat` — the only portal moves
        are admin Recall (request_changes) or Cancel. This test characterises the
        stuck-state; it must be updated when the gap is fixed.
        """
        t = self._drive_to_uat(self.subuser, "subuser:submit_ticket")
        self.assertEqual(t.requester, self.subuser)
        # sub-user confirm (signal — no status change)
        self._act(self.subuser, "subuser:ticket_transition", t,
                  expect_status=S.UAT, action="confirm")
        t.refresh_from_db()
        self.assertTrue(t.subuser_confirmed)
        self.assertTrue(self._notified(self.client_user, t, "confirm"))  # primary client
        self.assertTrue(self._notified(self.admin, t, "confirm"))
        # confirmed-variant labels render correctly for each role (matrix is fine)
        self.assertContains(self._detail(self.subuser, "subuser:ticket_detail", t),
                            "Confirmed — Awaiting Approval")
        self.assertContains(self._dash(self.client_user, "client_dashboard"),
                            "Ready for Your Review (sub-user confirmed)")
        self.assertContains(self._detail(self.admin, "admin_ticket_detail", t),
                            "UAT — sub-user confirmed, awaiting client approval")
        # SYMPTOM: client detail RENDERS Approve/Request Changes (org-scoped view)
        # — present-but-broken — but the POST is engine-rejected (ownership).
        cdetail = self._detail(self.client_user, "client_ticket_detail", t)
        self.assertContains(cdetail, 'value="approve"')
        self.assertContains(cdetail, 'value="request_changes"')
        self._act(self.client_user, "client_ticket_transition", t, action="approve")
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)  # client approve blocked → unchanged
        # admin `approve` is NOT exposed by the admin endpoint → unsupported.
        self._act(self.admin, "ticket_transition", t, action="approve")
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)  # admin approve unsupported → still stuck
        # The only forward move available to admin is Recall (→ development).
        self._act(self.admin, "ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="request_changes", feedback="No approve path; recalling.")

    def test_branch_subuser_still_broken(self):
        """Sub-user request_changes ('Still Broken') on their OWN uat ticket."""
        t = self._drive_to_uat(self.subuser, "subuser:submit_ticket")
        # sub-user IS the requester here, so guard_request_changes passes.
        self._act(self.subuser, "subuser:ticket_transition", t,
                  expect_status=S.IN_PROGRESS, expect_sub=SS.DEVELOPMENT,
                  action="request_changes", feedback="Export still empty")
        self.assertTrue(self._notified(self.developer, t, "request_changes"))
        self.assertContains(self._dash(self.developer, "dev:dashboard"), ">Development</span>")
        self.assertContains(self._detail(self.developer, "dev:ticket_detail", t),
                            'value="submit_for_testing"')
