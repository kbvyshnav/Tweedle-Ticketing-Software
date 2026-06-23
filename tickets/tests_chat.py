"""Chat / message posting (P0) — the write path for TicketMessage.

Covers the shared helper (`tickets/chat.post_ticket_message`) and every portal's
message-post endpoint: that the rightful participant can post, that object-level
scoping blocks everyone else (404), that wrong roles are blocked (403), that
GET is rejected (405), empty bodies are ignored, locked tickets refuse new
messages, and a posted message is visible across portals.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Client
from tickets.chat import ChatError, post_ticket_message
from tickets.models import Ticket

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus


class ChatHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Client.objects.create(name="Globomantics", code="GMEC")
        cls.user = User.objects.create_user("req_helper", role="client", client=cls.org)

    def _ticket(self, status=S.IN_PROGRESS, sub=SS.DEVELOPMENT):
        return Ticket.objects.create(
            subject="x", requester=self.user, client=self.org,
            status=status, sub_status=sub,
        )

    def test_empty_body_raises_and_creates_nothing(self):
        t = self._ticket()
        with self.assertRaises(ChatError):
            post_ticket_message(t, self.user, "   ")
        self.assertEqual(t.messages.count(), 0)

    def test_locked_statuses_raise(self):
        for st in (S.CLOSED, S.REJECTED, S.CANCELLED):
            t = self._ticket(status=st, sub=None)
            with self.assertRaises(ChatError):
                post_ticket_message(t, self.user, "hello")
            self.assertEqual(t.messages.count(), 0)

    def test_success_trims_and_creates(self):
        t = self._ticket()
        msg = post_ticket_message(t, self.user, "  hello world  ")
        self.assertEqual(msg.body, "hello world")
        self.assertEqual(msg.author, self.user)
        self.assertEqual(t.messages.count(), 1)


class ChatEndpointTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.other_org = Client.objects.create(name="Initech", code="INTC")

        self.admin = User.objects.create_user("admin_chat", role="admin")
        self.client_user = User.objects.create_user("client_chat", role="client", client=self.org)
        self.subuser = User.objects.create_user("subuser_chat", role="subuser", client=self.org)
        self.developer = User.objects.create_user("dev_chat", role="developer")
        self.tester = User.objects.create_user("tester_chat", role="tester")
        self.other_client = User.objects.create_user("other_chat", role="client", client=self.other_org)
        self.other_dev = User.objects.create_user("otherdev_chat", role="developer")

        # A client-submitted ticket, assigned to dev + tester, in testing.
        self.t_client = Ticket.objects.create(
            subject="client ticket", requester=self.client_user, client=self.org,
            assigned_developer=self.developer, assigned_tester=self.tester,
            status=S.IN_PROGRESS, sub_status=SS.TESTING,
        )
        # A sub-user-submitted ticket in the same org.
        self.t_subuser = Ticket.objects.create(
            subject="subuser ticket", requester=self.subuser, client=self.org,
            assigned_developer=self.developer, assigned_tester=self.tester,
            status=S.IN_PROGRESS, sub_status=SS.DEVELOPMENT,
        )

    # ── client ───────────────────────────────────────────────────────────
    def test_client_can_post_on_own_org_ticket(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse("client_post_message", args=[self.t_client.pk]), {"body": "hi team"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.t_client.messages.count(), 1)
        m = self.t_client.messages.first()
        self.assertEqual(m.author, self.client_user)
        self.assertEqual(m.body, "hi team")

    def test_client_cannot_post_other_org_ticket(self):
        self.client.force_login(self.other_client)
        resp = self.client.post(
            reverse("client_post_message", args=[self.t_client.pk]), {"body": "intrude"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.t_client.messages.count(), 0)

    def test_client_empty_body_creates_nothing(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse("client_post_message", args=[self.t_client.pk]), {"body": "   "}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.t_client.messages.count(), 0)

    def test_get_is_rejected(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("client_post_message", args=[self.t_client.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_wrong_role_is_blocked(self):
        self.client.force_login(self.developer)
        resp = self.client.post(
            reverse("client_post_message", args=[self.t_client.pk]), {"body": "x"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.t_client.messages.count(), 0)

    # ── sub-user ─────────────────────────────────────────────────────────
    def test_subuser_can_post_on_own_ticket(self):
        self.client.force_login(self.subuser)
        resp = self.client.post(
            reverse("subuser:post_message", args=[self.t_subuser.pk]), {"body": "from subuser"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.t_subuser.messages.count(), 1)

    def test_subuser_cannot_post_on_another_requesters_ticket(self):
        self.client.force_login(self.subuser)
        resp = self.client.post(
            reverse("subuser:post_message", args=[self.t_client.pk]), {"body": "x"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.t_client.messages.count(), 0)

    # ── developer ────────────────────────────────────────────────────────
    def test_developer_can_post_on_assigned_ticket(self):
        self.client.force_login(self.developer)
        resp = self.client.post(
            reverse("dev:post_message", args=[self.t_client.pk]), {"body": "dev here"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.t_client.messages.count(), 1)

    def test_developer_cannot_post_on_unassigned_ticket(self):
        self.client.force_login(self.other_dev)
        resp = self.client.post(
            reverse("dev:post_message", args=[self.t_client.pk]), {"body": "x"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.t_client.messages.count(), 0)

    # ── tester ───────────────────────────────────────────────────────────
    def test_tester_can_post_on_assigned_ticket(self):
        self.client.force_login(self.tester)
        resp = self.client.post(
            reverse("tester:post_message", args=[self.t_client.pk]), {"body": "tester here"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.t_client.messages.count(), 1)

    # ── admin ────────────────────────────────────────────────────────────
    def test_admin_can_post_on_any_ticket(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("admin_post_message", args=[self.t_client.pk]), {"body": "admin reply"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.t_client.messages.count(), 1)

    # ── locked + cross-portal ────────────────────────────────────────────
    def test_locked_ticket_refuses_message_via_endpoint(self):
        locked = Ticket.objects.create(
            subject="closed one", requester=self.client_user, client=self.org,
            status=S.CLOSED, sub_status=None,
        )
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse("client_post_message", args=[locked.pk]), {"body": "too late"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(locked.messages.count(), 0)

    def test_message_is_visible_across_portals(self):
        self.client.force_login(self.client_user)
        self.client.post(
            reverse("client_post_message", args=[self.t_client.pk]), {"body": "cross portal hi"}
        )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_ticket_chat", args=[self.t_client.pk]))
        self.assertContains(resp, "cross portal hi")
