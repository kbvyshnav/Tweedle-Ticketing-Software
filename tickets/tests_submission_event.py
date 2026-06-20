"""Tests for the creation-time "submitted" timeline event (Step A / Issue 4).

Every created ticket gets exactly one `submitted` TicketEvent via a post_save
signal, so every portal's timeline starts at "Ticket Submitted" (TARGET §7).
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.models import Ticket
from tickets.transitions import transition

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus

SUBMIT_DATA = {
    "subject": "Export downloads an empty file",
    "description": "When I click Export the downloaded file is empty.",
    "category": "Bug",
    "priority": "high",
}


class SubmissionEventBase(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.admin = User.objects.create_user("admin_se", role="admin")
        self.client_user = User.objects.create_user(
            "client_se", role="client", client=self.org
        )
        self.subuser = User.objects.create_user(
            "subuser_se", role="subuser", client=self.org
        )
        self.developer = User.objects.create_user("dev_se", role="developer")
        self.tester = User.objects.create_user("tester_se", role="tester")

    def _make(self, status=S.NEW, sub_status=None, requester=None, **kw):
        return Ticket.objects.create(
            subject="A ticket", description="Body text here.",
            requester=requester or self.client_user, client=self.org,
            status=status, sub_status=sub_status, **kw,
        )


class SubmissionEventCreationTests(SubmissionEventBase):
    def test_create_writes_exactly_one_submitted_event(self):
        t = self._make()
        evs = t.events.filter(action="submitted")
        self.assertEqual(evs.count(), 1)
        ev = evs.first()
        self.assertEqual(ev.actor, self.client_user)   # the requester
        self.assertEqual(ev.to_status, "new")
        self.assertEqual(ev.from_status, "")
        # It sorts first in the timeline.
        self.assertEqual(t.events.first().action, "submitted")

    def test_client_submit_view_writes_submitted_event(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse("client_submit_ticket"), SUBMIT_DATA)
        self.assertEqual(resp.status_code, 302)
        t = Ticket.objects.filter(requester=self.client_user).latest("created_at")
        self.assertEqual(t.events.filter(action="submitted").count(), 1)

    def test_subuser_submit_view_writes_submitted_event(self):
        self.client.force_login(self.subuser)
        resp = self.client.post(reverse("subuser:submit_ticket"), SUBMIT_DATA)
        self.assertEqual(resp.status_code, 302)
        t = Ticket.objects.filter(requester=self.subuser).latest("created_at")
        self.assertEqual(t.events.filter(action="submitted").count(), 1)

    def test_restore_does_not_add_a_second_submitted_event(self):
        t = self._make(status=S.REJECTED)
        self.assertEqual(t.events.filter(action="submitted").count(), 1)
        transition(t, "restore", self.admin)  # rejected -> new (a transition, not a creation)
        t.refresh_from_db()
        self.assertEqual(t.events.filter(action="submitted").count(), 1)
        self.assertEqual(t.events.filter(action="restore").count(), 1)


class SeedDemoSubmissionEventTests(TestCase):
    def test_seed_demo_every_ticket_has_one_submission_event(self):
        call_command("seed_demo", verbosity=0)
        self.assertTrue(Ticket.objects.exists())
        for t in Ticket.objects.all():
            self.assertEqual(
                t.events.filter(action="submitted").count(), 1,
                f"{t.reference} should have exactly one submission event",
            )


class SubmissionTimelineRenderTests(SubmissionEventBase):
    def test_client_timeline_shows_submitted_once(self):
        t = self._make()  # new ticket → only the submission event
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("client_ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Ticket Submitted", count=1)

    def test_developer_timeline_shows_submitted(self):
        t = self._make(status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT,
                       assigned_developer=self.developer)
        self.client.force_login(self.developer)
        resp = self.client.get(reverse("dev:ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Ticket Submitted")

    def test_tester_timeline_shows_submitted(self):
        t = self._make(status=S.IN_PROGRESS, sub_status=SS.TESTING,
                       assigned_developer=self.developer, assigned_tester=self.tester)
        self.client.force_login(self.tester)
        resp = self.client.get(reverse("tester:ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Ticket Submitted")

    def test_subuser_timeline_shows_submitted(self):
        t = self._make(requester=self.subuser)
        self.client.force_login(self.subuser)
        resp = self.client.get(reverse("subuser:ticket_detail", args=[t.pk]))
        self.assertContains(resp, "Ticket Submitted")

    def test_admin_drawer_shows_submitted_and_friendly_labels(self):
        t = self._make()
        transition(t, "assign", self.admin, developer=self.developer)  # adds an "assign" event
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_ticket_timeline", args=[t.pk]))
        self.assertContains(resp, "Ticket Submitted")
        # The drawer now renders friendly labels, not the raw action name.
        self.assertContains(resp, "Assigned to Developer")
