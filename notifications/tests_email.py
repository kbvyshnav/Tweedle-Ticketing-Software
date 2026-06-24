"""Tests for the email-notification layer (notifications/email.py + signals.py)."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from accounts.models import Client
from admin_portal.models import OrganisationSettings
from notifications.email import _is_enabled
from notifications.models import Notification
from tickets.models import Ticket
from tickets.transitions import transition

User = get_user_model()
S = Ticket.Status


class EmailToggleLogicTests(TestCase):
    """The pure pref-consulting logic, independent of sending."""

    def test_unmapped_action_always_enabled(self):
        self.assertTrue(_is_enabled("reject", "admin"))

    def test_client_and_subuser_always_enabled(self):
        self.assertTrue(_is_enabled("close", "client"))
        self.assertTrue(_is_enabled("close", "subuser"))

    def test_mapped_action_defaults_enabled(self):
        self.assertTrue(_is_enabled("assign", "developer"))
        self.assertTrue(_is_enabled("close", "admin"))

    def test_assignee_toggle_off_disables(self):
        s = OrganisationSettings.load()
        s.notification_prefs = {"assigned_assignee": False}
        s.save()
        self.assertFalse(_is_enabled("assign", "developer"))
        # The admin audience for the same event is untouched.
        self.assertTrue(_is_enabled("assign", "admin"))

    def test_admin_toggle_off_disables(self):
        s = OrganisationSettings.load()
        s.notification_prefs = {"closed_admin": False}
        s.save()
        self.assertFalse(_is_enabled("close", "admin"))


class EmailDeliveryTests(TestCase):
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

    def _make_new_ticket(self, capture=False):
        if capture:
            with self.captureOnCommitCallbacks(execute=True):
                return Ticket.objects.create(
                    subject="Broken export", requester=self.requester,
                    client=self.org, status=S.NEW,
                )
        return Ticket.objects.create(
            subject="Broken export", requester=self.requester,
            client=self.org, status=S.NEW,
        )

    def test_new_ticket_emails_admin_not_requester(self):
        mail.outbox = []
        self._make_new_ticket(capture=True)
        recipients = [addr for m in mail.outbox for addr in m.to]
        self.assertIn(self.admin.email, recipients)
        self.assertNotIn(self.requester.email, recipients)

    def test_assign_emails_the_developer(self):
        ticket = self._make_new_ticket()  # not captured -> no email yet
        mail.outbox = []
        with self.captureOnCommitCallbacks(execute=True):
            transition(ticket, "assign", actor=self.admin, developer=self.dev)
        recipients = [addr for m in mail.outbox for addr in m.to]
        self.assertIn(self.dev.email, recipients)

    def test_assignee_toggle_off_suppresses_developer_email(self):
        s = OrganisationSettings.load()
        s.notification_prefs = {"assigned_assignee": False}
        s.save()
        ticket = self._make_new_ticket()
        mail.outbox = []
        with self.captureOnCommitCallbacks(execute=True):
            transition(ticket, "assign", actor=self.admin, developer=self.dev)
        recipients = [addr for m in mail.outbox for addr in m.to]
        self.assertNotIn(self.dev.email, recipients)

    def test_no_email_when_recipient_has_no_address(self):
        self.dev.email = ""
        self.dev.save()
        ticket = self._make_new_ticket()
        mail.outbox = []
        with self.captureOnCommitCallbacks(execute=True):
            transition(ticket, "assign", actor=self.admin, developer=self.dev)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_body_links_and_subject(self):
        ticket = self._make_new_ticket()
        mail.outbox = []
        with self.captureOnCommitCallbacks(execute=True):
            transition(ticket, "assign", actor=self.admin, developer=self.dev)
        msg = mail.outbox[0]
        self.assertIn(ticket.reference, msg.subject)
        self.assertIn("/notifications/", msg.body)
