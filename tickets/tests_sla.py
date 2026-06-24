"""Tests for the resolution-time SLA: due dates, overdue, the pause-aware clock,
and the developer dashboard surfacing (tickets/sla.py)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Client
from tickets import sla
from tickets.models import Ticket
from tickets.transitions import transition

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class SlaModuleTests(TestCase):
    """The pure functions in tickets/sla.py."""

    def test_target_days_by_priority(self):
        self.assertEqual(sla.target_days("high"), 3)
        self.assertEqual(sla.target_days("medium"), 5)
        self.assertEqual(sla.target_days("low"), 7)

    def test_target_days_unknown_falls_back(self):
        self.assertEqual(sla.target_days("bogus"), sla.DEFAULT_TARGET_DAYS)

    def test_admin_reports_share_the_same_targets(self):
        # The Reports TAT convention must be the very same object (no drift).
        from admin_portal.views import TAT_TARGET_DAYS
        self.assertIs(TAT_TARGET_DAYS, sla.RESOLUTION_TARGET_DAYS)


class SlaModelTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.requester = User.objects.create_user(
            "cli", email="cli@test.local", password="pw", role="client",
            client=self.org,
        )

    def _ticket(self, **kw):
        kw.setdefault("subject", "S")
        kw.setdefault("requester", self.requester)
        kw.setdefault("client", self.org)
        return Ticket.objects.create(**kw)

    def test_due_at_set_on_creation_from_priority(self):
        t = self._ticket(priority="high", status=S.NEW)
        self.assertIsNotNone(t.sla_due_at)
        expected = t.created_at + timedelta(days=3)
        self.assertAlmostEqual(
            t.sla_due_at, expected, delta=timedelta(seconds=5)
        )

    def test_overdue_true_when_running_and_past_due(self):
        t = self._ticket(status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT)
        t.sla_due_at = timezone.now() - timedelta(hours=1)
        self.assertTrue(t.is_overdue)

    def test_not_overdue_when_due_in_future(self):
        t = self._ticket(status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT)
        t.sla_due_at = timezone.now() + timedelta(days=1)
        self.assertFalse(t.is_overdue)

    def test_paused_statuses_never_overdue(self):
        past = timezone.now() - timedelta(days=10)
        for status in (S.AWAITING_CLIENT, S.UAT):
            t = self._ticket(status=status)
            t.sla_due_at = past
            self.assertFalse(t.is_overdue, status)

    def test_terminal_statuses_never_overdue(self):
        past = timezone.now() - timedelta(days=10)
        for status in (S.RESOLVED, S.CLOSED, S.REJECTED, S.CANCELLED):
            t = self._ticket(status=status)
            t.sla_due_at = past
            self.assertFalse(t.is_overdue, status)


class SlaClockEngineTests(TestCase):
    """The pause/resume/reset clock as driven by transition()."""

    def setUp(self):
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.admin = User.objects.create_user(
            "adm", email="adm@test.local", password="pw", role="admin"
        )
        self.dev = User.objects.create_user(
            "dev", email="dev@test.local", password="pw", role="developer"
        )
        self.requester = User.objects.create_user(
            "cli", email="cli@test.local", password="pw", role="client",
            client=self.org,
        )

    def _in_progress_ticket(self):
        t = Ticket.objects.create(
            subject="S", requester=self.requester, client=self.org,
            priority="medium", status=S.NEW,
        )
        transition(t, "assign", actor=self.admin, developer=self.dev)
        return t

    def test_request_info_pauses_the_clock(self):
        t = self._in_progress_ticket()
        self.assertIsNone(t.sla_paused_at)
        transition(t, "request_info", actor=self.admin, message="Need detail")
        t.refresh_from_db()
        self.assertEqual(t.status, S.AWAITING_CLIENT)
        self.assertIsNotNone(t.sla_paused_at)

    def test_resume_extends_deadline_by_paused_duration(self):
        t = self._in_progress_ticket()
        due_before = t.sla_due_at
        transition(t, "request_info", actor=self.admin, message="Need detail")
        t.refresh_from_db()
        # Simulate two days spent paused.
        t.sla_paused_at = timezone.now() - timedelta(days=2)
        t.save(update_fields=["sla_paused_at"])
        transition(t, "resume", actor=self.admin)
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertIsNone(t.sla_paused_at)
        # Deadline pushed ~2 days forward, so paused time didn't burn the budget.
        self.assertGreaterEqual(t.sla_due_at, due_before + timedelta(days=2) - timedelta(minutes=1))

    def test_reopen_resets_to_a_fresh_future_deadline(self):
        t = self._in_progress_ticket()
        # Drive to resolved, then closed (a finished/terminal state).
        transition(t, "request_info", actor=self.admin, message="q")
        transition(t, "resume", actor=self.admin)
        # Force a stale deadline and a terminal status, then reopen.
        Ticket.objects.filter(pk=t.pk).update(
            status=S.CLOSED, sub_status=None,
            sla_due_at=timezone.now() - timedelta(days=30),
        )
        t.refresh_from_db()
        transition(t, "reopen", actor=self.admin, reason="re-check")
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)
        self.assertGreater(t.sla_due_at, timezone.now())


class SlaDashboardTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.dev = User.objects.create_user(
            "dev", email="dev@test.local", password="pw", role="developer"
        )
        self.requester = User.objects.create_user(
            "cli", email="cli@test.local", password="pw", role="client",
            client=self.org,
        )
        self.client.force_login(self.dev)

    def _ticket(self, due_offset_days, status=S.IN_PROGRESS):
        t = Ticket.objects.create(
            subject="S", requester=self.requester, client=self.org,
            status=status, sub_status=SS.DEVELOPMENT if status == S.IN_PROGRESS else None,
            assigned_developer=self.dev,
        )
        Ticket.objects.filter(pk=t.pk).update(
            sla_due_at=timezone.now() + timedelta(days=due_offset_days)
        )
        return Ticket.objects.get(pk=t.pk)

    def test_overdue_count_reflects_only_running_breached_tickets(self):
        self._ticket(-1)                       # overdue
        self._ticket(-2)                       # overdue
        self._ticket(+3)                       # not yet due
        self._ticket(-5, status=S.AWAITING_CLIENT)  # paused → never overdue
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertEqual(resp.context["overdue_count"], 2)

    def test_row_renders_data_overdue_true(self):
        self._ticket(-1)
        resp = self.client.get(reverse("dev:dashboard"))
        self.assertContains(resp, 'data-overdue="true"')
        self.assertContains(resp, "dev-overdue-pill")
