from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Client
from notifications.models import Notification

from .models import Ticket, TicketEvent
from .transitions import (
    InvalidTransition,
    TransitionNotAllowed,
    TransitionValidationError,
    transition,
)

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class EngineTestBase(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.admin = User.objects.create_user("admin1", role="admin")
        self.client_user = User.objects.create_user(
            "client1", role="client", client=self.org
        )
        self.subuser = User.objects.create_user(
            "sub1", role="subuser", client=self.org
        )
        self.developer = User.objects.create_user("dev1", role="developer")
        self.developer2 = User.objects.create_user("dev2", role="developer")
        self.tester = User.objects.create_user("qa1", role="tester")

    def make_ticket(self, status=S.NEW, sub_status=None, requester=None, **kw):
        return Ticket.objects.create(
            subject="Login is broken",
            requester=requester or self.client_user,
            client=self.org,
            status=status,
            sub_status=sub_status,
            **kw,
        )

    # ── convenience builders for mid-lifecycle states ──────────────────
    def in_development(self, tester=None):
        return self.make_ticket(
            status=S.IN_PROGRESS,
            sub_status=SS.DEVELOPMENT,
            assigned_developer=self.developer,
            assigned_tester=tester,
        )

    def in_testing(self):
        return self.make_ticket(
            status=S.IN_PROGRESS,
            sub_status=SS.TESTING,
            assigned_developer=self.developer,
            assigned_tester=self.tester,
        )

    def in_uat(self):
        return self.make_ticket(status=S.UAT, sub_status=None,
                                assigned_developer=self.developer)


class ReferenceTests(EngineTestBase):
    def test_reference_scheme(self):
        t = self.make_ticket()
        now = timezone.now()
        self.assertTrue(t.reference.startswith(f"GMEC{now:%y%m}"))
        self.assertTrue(t.reference.endswith("0001"))

    def test_reference_sequence_increments(self):
        t1 = self.make_ticket()
        t2 = self.make_ticket()
        self.assertEqual(int(t2.reference[-4:]), int(t1.reference[-4:]) + 1)

    def test_internal_ticket_uses_twdl_code(self):
        t = Ticket.objects.create(subject="x", requester=self.admin, client=None)
        self.assertTrue(t.reference.startswith("TWDL"))


class LegalTransitionTests(EngineTestBase):
    def test_assign_lands_in_development(self):
        t = self.make_ticket()
        transition(t, "assign", self.admin, developer=self.developer)
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertEqual(t.assigned_developer, self.developer)
        self.assertEqual(t.events.count(), 1)

    def test_happy_path_with_tester(self):
        t = self.make_ticket()
        transition(t, "assign", self.admin,
                   developer=self.developer, tester=self.tester)
        transition(t, "submit_for_testing", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.TESTING)
        transition(t, "pass", self.tester)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.READY_FOR_UAT)
        transition(t, "send_to_uat", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)
        self.assertIsNone(t.sub_status)
        transition(t, "approve", self.client_user)
        t.refresh_from_db()
        self.assertEqual(t.status, S.RESOLVED)
        self.assertIsNotNone(t.accepted_at)
        self.assertEqual(t.accepted_by, self.client_user)
        transition(t, "close", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CLOSED)
        self.assertIsNotNone(t.closed_at)

    def test_happy_path_without_tester_mark_ready(self):
        t = self.in_development()  # no tester
        transition(t, "mark_ready", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.READY_FOR_UAT)
        transition(t, "send_to_uat", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)

    def test_fail_returns_then_resubmit(self):
        t = self.in_testing()
        transition(t, "fail", self.tester, failure_notes="Crashes on submit")
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.RETURNED)
        transition(t, "resubmit_for_testing", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.TESTING)

    def test_request_info_then_resume_restores_sub_status(self):
        t = self.in_testing()
        transition(t, "request_info", self.admin, message="Need more detail")
        t.refresh_from_db()
        self.assertEqual(t.status, S.AWAITING_CLIENT)
        self.assertIsNone(t.sub_status)
        self.assertEqual(t.paused_sub_status, SS.TESTING)
        transition(t, "resume", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.TESTING)
        self.assertIsNone(t.paused_sub_status)

    def test_request_changes_from_uat(self):
        t = self.in_uat()
        t.subuser_confirmed = True
        t.save()
        transition(t, "request_changes", self.client_user, feedback="Still wrong")
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertFalse(t.subuser_confirmed)

    def test_reject_then_restore(self):
        t = self.make_ticket()
        transition(t, "reject", self.admin, reason="Out of scope")
        t.refresh_from_db()
        self.assertEqual(t.status, S.REJECTED)
        transition(t, "restore", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)

    def test_cancel_by_requester(self):
        t = self.make_ticket()
        transition(t, "cancel", self.client_user)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)
        self.assertIsNone(t.sub_status)

    def test_cancel_from_in_progress(self):
        t = self.in_development()  # in_progress + development
        transition(t, "cancel", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)
        self.assertIsNone(t.sub_status)

    def test_cancel_from_awaiting_client(self):
        t = self.make_ticket(status=S.AWAITING_CLIENT, sub_status=None)
        transition(t, "cancel", self.client_user)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)
        self.assertIsNone(t.sub_status)

    def test_admin_can_cancel_ticket_it_does_not_own(self):
        # requester is self.client_user; the admin is not the requester.
        t = self.in_development()
        self.assertNotEqual(t.requester, self.admin)
        transition(t, "cancel", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CANCELLED)
        self.assertIsNone(t.sub_status)


class ConfirmAndReassignTests(EngineTestBase):
    def test_subuser_confirm_signal(self):
        t = self.make_ticket(status=S.UAT, requester=self.subuser)
        transition(t, "confirm", self.subuser)
        t.refresh_from_db()
        self.assertTrue(t.subuser_confirmed)
        self.assertEqual(t.status, S.UAT)  # no status change
        self.assertEqual(t.events.filter(action="confirm").count(), 1)

    def test_reassign_changes_developer_only(self):
        t = self.in_development()
        transition(t, "reassign", self.admin, developer=self.developer2)
        t.refresh_from_db()
        self.assertEqual(t.assigned_developer, self.developer2)
        self.assertEqual(t.status, S.IN_PROGRESS)  # unchanged
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)
        self.assertEqual(t.events.filter(action="reassigned").count(), 1)

    def test_reassign_requires_an_assignee(self):
        t = self.in_development()
        with self.assertRaises(TransitionValidationError):
            transition(t, "reassign", self.admin)


class GuardTests(EngineTestBase):
    def test_mark_ready_blocked_when_tester_assigned(self):
        t = self.in_development(tester=self.tester)
        with self.assertRaises(InvalidTransition):
            transition(t, "mark_ready", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)  # unchanged
        self.assertEqual(t.events.count(), 0)

    def test_submit_for_testing_requires_tester(self):
        t = self.in_development()  # no tester
        with self.assertRaises(InvalidTransition):
            transition(t, "submit_for_testing", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)

    def test_adding_tester_later_disables_mark_ready(self):
        t = self.in_development()  # no tester yet
        transition(t, "reassign", self.admin, tester=self.tester)
        t.refresh_from_db()
        with self.assertRaises(InvalidTransition):
            transition(t, "mark_ready", self.developer)
        # but submit_for_testing is now the legal route
        transition(t, "submit_for_testing", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.sub_status, SS.TESTING)


class ReopenTests(EngineTestBase):
    def _resolved(self):
        return self.make_ticket(status=S.RESOLVED,
                                assigned_developer=self.developer)

    def _closed(self, days_ago=0):
        return self.make_ticket(
            status=S.CLOSED,
            assigned_developer=self.developer,
            closed_at=timezone.now() - timedelta(days=days_ago),
        )

    def test_client_reopen_resolved_anytime(self):
        t = self._resolved()
        transition(t, "reopen", self.client_user, reason="Broke again")
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)

    def test_client_reopen_closed_within_window(self):
        t = self._closed(days_ago=3)
        transition(t, "reopen", self.client_user, reason="Regression")
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)

    def test_client_reopen_closed_past_window_raises(self):
        t = self._closed(days_ago=30)
        with self.assertRaises(InvalidTransition):
            transition(t, "reopen", self.client_user, reason="Too late")
        t.refresh_from_db()
        self.assertEqual(t.status, S.CLOSED)  # unchanged

    def test_admin_reopen_closed_anytime(self):
        t = self._closed(days_ago=300)
        transition(t, "reopen", self.admin, reason="Admin override")
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)

    def test_reopen_resolved_reroutes_to_original_developer(self):
        t = self._resolved()  # assigned_developer = self.developer
        transition(t, "reopen", self.client_user, reason="Broke again")
        t.refresh_from_db()
        self.assertEqual(t.assigned_developer, self.developer)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)

    def test_reopen_closed_reroutes_to_original_developer(self):
        t = self._closed(days_ago=2)  # assigned_developer = self.developer
        transition(t, "reopen", self.admin, reason="Regression")
        t.refresh_from_db()
        self.assertEqual(t.assigned_developer, self.developer)
        self.assertEqual(t.sub_status, SS.DEVELOPMENT)


class AuthorizationTests(EngineTestBase):
    def test_developer_cannot_close(self):
        t = self.make_ticket(status=S.RESOLVED)
        with self.assertRaises(TransitionNotAllowed):
            transition(t, "close", self.developer)
        t.refresh_from_db()
        self.assertEqual(t.status, S.RESOLVED)
        self.assertEqual(t.events.count(), 0)

    def test_client_cannot_assign(self):
        t = self.make_ticket()
        with self.assertRaises(TransitionNotAllowed):
            transition(t, "assign", self.client_user, developer=self.developer)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)

    def test_non_requester_client_cannot_approve(self):
        other = User.objects.create_user("client2", role="client", client=self.org)
        t = self.in_uat()  # requester is self.client_user
        with self.assertRaises(TransitionNotAllowed):
            transition(t, "approve", other)
        t.refresh_from_db()
        self.assertEqual(t.status, S.UAT)


class IllegalTransitionTests(EngineTestBase):
    def test_approve_from_new_is_illegal_and_unchanged(self):
        t = self.make_ticket()
        with self.assertRaises(InvalidTransition):
            transition(t, "approve", self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)
        self.assertEqual(t.events.count(), 0)

    def test_unknown_action_raises(self):
        t = self.make_ticket()
        with self.assertRaises(InvalidTransition):
            transition(t, "frobnicate", self.admin)

    def test_missing_required_field_raises_and_unchanged(self):
        t = self.make_ticket()
        with self.assertRaises(TransitionValidationError):
            transition(t, "reject", self.admin)  # missing reason
        t.refresh_from_db()
        self.assertEqual(t.status, S.NEW)
        self.assertEqual(t.events.count(), 0)


class AuditAndNotificationTests(EngineTestBase):
    def test_exactly_one_event_per_transition(self):
        t = self.make_ticket()
        transition(t, "assign", self.admin,
                   developer=self.developer, tester=self.tester)
        transition(t, "submit_for_testing", self.developer)
        transition(t, "pass", self.tester)
        self.assertEqual(TicketEvent.objects.filter(ticket=t).count(), 3)

    def test_event_records_from_and_to(self):
        t = self.make_ticket()
        transition(t, "assign", self.admin, developer=self.developer)
        ev = t.events.latest("id")
        self.assertEqual(ev.from_status, S.NEW)
        self.assertIsNone(ev.from_sub_status)
        self.assertEqual(ev.to_status, S.IN_PROGRESS)
        self.assertEqual(ev.to_sub_status, SS.DEVELOPMENT)

    def test_assign_notifies_developer(self):
        t = self.make_ticket()
        transition(t, "assign", self.admin, developer=self.developer)
        self.assertEqual(
            Notification.objects.filter(recipient=self.developer).count(), 1
        )

    def test_pass_notifies_admin(self):
        t = self.in_testing()
        transition(t, "pass", self.tester)
        self.assertEqual(
            Notification.objects.filter(recipient=self.admin, action="pass").count(),
            1,
        )

    def test_failed_transition_creates_no_notification(self):
        t = self.make_ticket(status=S.RESOLVED)
        with self.assertRaises(TransitionNotAllowed):
            transition(t, "close", self.developer)
        self.assertEqual(Notification.objects.count(), 0)


class ConstraintTests(EngineTestBase):
    def test_constraint_rejects_inconsistent_row(self):
        t = self.in_development()  # in_progress + development (valid)
        t.status = S.RESOLVED      # resolved + non-null sub_status (invalid)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                t.save()

    def test_constraint_rejects_in_progress_without_sub_status(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_ticket(status=S.IN_PROGRESS, sub_status=None)
