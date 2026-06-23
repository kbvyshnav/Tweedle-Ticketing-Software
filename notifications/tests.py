"""Notification feed, read-state endpoints, and chat-message notifications (P1)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from notifications.models import Notification
from tickets.chat import post_ticket_message
from tickets.models import Ticket

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class NotificationFeedTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.other_org = Client.objects.create(name="Initech", code="INTC")
        self.client_user = User.objects.create_user("client_n", role="client", client=self.org)
        self.other_client = User.objects.create_user("other_n", role="client", client=self.other_org)
        self.admin = User.objects.create_user("admin_n", role="admin")
        self.ticket = Ticket.objects.create(
            subject="t", requester=self.client_user, client=self.org, status=S.NEW
        )

    def _notif(self, recipient, is_read=False, message="something happened"):
        return Notification.objects.create(
            recipient=recipient, ticket=self.ticket, actor=self.admin,
            action="assign", message=message, is_read=is_read,
        )

    def test_feed_lists_only_own_notifications(self):
        mine = self._notif(self.client_user)
        theirs = self._notif(self.other_client)
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("notifications_feed"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "notifications/feed.html")
        ids = [n.pk for n in resp.context["notifications"]]
        self.assertIn(mine.pk, ids)
        self.assertNotIn(theirs.pk, ids)

    def test_feed_requires_login(self):
        resp = self.client.get(reverse("notifications_feed"))
        self.assertEqual(resp.status_code, 302)  # redirect to login

    def test_open_marks_read_and_redirects_to_ticket(self):
        n = self._notif(self.client_user)
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("notification_open", args=[n.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("client_ticket_detail", args=[self.ticket.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_open_others_notification_is_404(self):
        n = self._notif(self.other_client)
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("notification_open", args=[n.pk]))
        self.assertEqual(resp.status_code, 404)
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_admin_open_redirects_to_dashboard(self):
        n = self._notif(self.admin)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("notification_open", args=[n.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("admin_dashboard"), resp.url)

    def test_mark_all_read(self):
        self._notif(self.client_user)
        self._notif(self.client_user)
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse("notifications_mark_all_read"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(recipient=self.client_user, is_read=False).count(), 0
        )

    def test_mark_all_read_only_affects_own(self):
        self._notif(self.client_user)
        theirs = self._notif(self.other_client)
        self.client.force_login(self.client_user)
        self.client.post(reverse("notifications_mark_all_read"))
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)

    def test_mark_all_read_requires_post(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("notifications_mark_all_read"))
        self.assertEqual(resp.status_code, 405)

    def test_bell_renders_real_data_in_client_portal(self):
        self._notif(self.client_user, message="Your ticket was assigned")
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("client_dashboard"))
        self.assertContains(resp, "Your ticket was assigned")
        self.assertContains(resp, reverse("notifications_feed"))
        self.assertContains(resp, 'id="notifCount"')


class ChatNotificationTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.client_user = User.objects.create_user("client_cn", role="client", client=self.org)
        self.developer = User.objects.create_user("dev_cn", role="developer")
        self.tester = User.objects.create_user("tester_cn", role="tester")
        self.admin = User.objects.create_user("admin_cn", role="admin")
        self.ticket = Ticket.objects.create(
            subject="t", requester=self.client_user, client=self.org,
            assigned_developer=self.developer, assigned_tester=self.tester,
            status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT,
        )

    def test_posting_message_notifies_other_participants(self):
        post_ticket_message(self.ticket, self.client_user, "hello")
        recipients = set(
            Notification.objects.filter(ticket=self.ticket, action="message")
            .values_list("recipient", flat=True)
        )
        self.assertIn(self.developer.pk, recipients)
        self.assertIn(self.tester.pk, recipients)
        self.assertIn(self.admin.pk, recipients)
        # the author is never notified about their own message
        self.assertNotIn(self.client_user.pk, recipients)

    def test_developer_message_notifies_requester_not_author(self):
        post_ticket_message(self.ticket, self.developer, "from dev")
        self.assertFalse(
            Notification.objects.filter(recipient=self.developer, action="message").exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.client_user, action="message").exists()
        )
