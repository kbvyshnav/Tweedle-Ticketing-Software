"""Tests for the SLA cron jobs: close_stale_resolved + notify_overdue."""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Client
from notifications.models import Notification
from tickets.models import Ticket, TicketEvent

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class CloseStaleResolvedTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Acme", code="ACME")
        self.admin = User.objects.create_user(
            "adm", email="adm@test.local", password="pw", role="admin"
        )
        self.requester = User.objects.create_user(
            "cli", email="cli@test.local", password="pw", role="client",
            client=self.org,
        )

    def _resolved(self, resolved_days_ago):
        t = Ticket.objects.create(
            subject="S", requester=self.requester, client=self.org,
            status=S.RESOLVED, sub_status=None,
        )
        ev = TicketEvent.objects.create(
            ticket=t, actor=self.admin, action="approve",
            from_status=S.UAT, to_status=S.RESOLVED,
        )
        TicketEvent.objects.filter(pk=ev.pk).update(
            created_at=timezone.now() - timedelta(days=resolved_days_ago)
        )
        return t

    def _run(self, *args):
        out = StringIO()
        call_command("close_stale_resolved", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_stale_resolved_is_closed(self):
        t = self._resolved(resolved_days_ago=10)  # default window is 7
        self._run()
        t.refresh_from_db()
        self.assertEqual(t.status, S.CLOSED)
        self.assertIsNotNone(t.closed_at)
        # Went through the engine -> a close event exists.
        self.assertTrue(t.events.filter(to_status=S.CLOSED).exists())

    def test_recent_resolved_is_left_alone(self):
        t = self._resolved(resolved_days_ago=2)
        self._run()
        t.refresh_from_db()
        self.assertEqual(t.status, S.RESOLVED)

    def test_days_override(self):
        t = self._resolved(resolved_days_ago=5)
        self._run("--days", "3")
        t.refresh_from_db()
        self.assertEqual(t.status, S.CLOSED)

    def test_dry_run_changes_nothing(self):
        t = self._resolved(resolved_days_ago=10)
        out = self._run("--dry-run")
        t.refresh_from_db()
        self.assertEqual(t.status, S.RESOLVED)
        self.assertIn("would close", out.lower())

    def test_non_resolved_untouched(self):
        t = Ticket.objects.create(
            subject="S", requester=self.requester, client=self.org,
            status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT,
        )
        self._run()
        t.refresh_from_db()
        self.assertEqual(t.status, S.IN_PROGRESS)


class NotifyOverdueTests(TestCase):
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

    def _ticket(self, due_offset_days, status=S.IN_PROGRESS, notified=False):
        t = Ticket.objects.create(
            subject="S", requester=self.requester, client=self.org,
            status=status,
            sub_status=SS.DEVELOPMENT if status == S.IN_PROGRESS else None,
            assigned_developer=self.dev if status == S.IN_PROGRESS else None,
        )
        Ticket.objects.filter(pk=t.pk).update(
            sla_due_at=timezone.now() + timedelta(days=due_offset_days),
            overdue_notified=notified,
        )
        return Ticket.objects.get(pk=t.pk)

    def _run(self, *args):
        out = StringIO()
        call_command("notify_overdue", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_overdue_warns_dev_and_admin_and_sets_flag(self):
        t = self._ticket(due_offset_days=-1)
        self._run()
        actions = Notification.objects.filter(ticket=t, action="overdue")
        recipients = set(actions.values_list("recipient", flat=True))
        self.assertEqual(recipients, {self.dev.pk, self.admin.pk})
        # Client is never warned about an internal SLA breach.
        self.assertNotIn(self.requester.pk, recipients)
        t.refresh_from_db()
        self.assertTrue(t.overdue_notified)

    def test_second_run_is_idempotent(self):
        self._ticket(due_offset_days=-1)
        self._run()
        before = Notification.objects.filter(action="overdue").count()
        self._run()
        after = Notification.objects.filter(action="overdue").count()
        self.assertEqual(before, after)

    def test_not_yet_due_is_not_warned(self):
        self._ticket(due_offset_days=+3)
        self._run()
        self.assertEqual(Notification.objects.filter(action="overdue").count(), 0)

    def test_paused_status_not_warned(self):
        # awaiting_client is not a running status -> never overdue.
        self._ticket(due_offset_days=-5, status=S.AWAITING_CLIENT)
        self._run()
        self.assertEqual(Notification.objects.filter(action="overdue").count(), 0)

    def test_dry_run_creates_no_notifications(self):
        t = self._ticket(due_offset_days=-1)
        out = self._run("--dry-run")
        self.assertEqual(Notification.objects.filter(action="overdue").count(), 0)
        t.refresh_from_db()
        self.assertFalse(t.overdue_notified)
        self.assertIn("would warn", out.lower())
