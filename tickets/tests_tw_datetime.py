"""Tests for the single Tweedle date/time format filter (Issue 3 / S5).

`tw_datetime` (tickets/templatetags/ticket_labels.py) is the ONE format —
"d M Y, g:i A" → "20 Jun 2026, 2:00 PM" — used for every ticket timestamp across
all five portals + admin. These tests pin TIME_ZONE so the rendered string is
deterministic (USE_TZ=True; Django's date filter localizes to the active zone).
"""

from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Client
from tickets.models import Ticket, TicketEvent
from tickets.templatetags.ticket_labels import tw_datetime

User = get_user_model()

# 2026-06-20 14:00 UTC → "20 Jun 2026, 2:00 PM" in the standard format.
PINNED = datetime(2026, 6, 20, 14, 0, tzinfo=dt_timezone.utc)
PINNED_STR = "20 Jun 2026, 2:00 PM"


@override_settings(TIME_ZONE="UTC", USE_TZ=True)
class TwDatetimeFilterTests(TestCase):
    def test_pm_datetime_renders_standard_format(self):
        self.assertEqual(tw_datetime(PINNED), PINNED_STR)

    def test_am_datetime_renders_standard_format(self):
        dt = datetime(2026, 6, 20, 9, 5, tzinfo=dt_timezone.utc)
        self.assertEqual(tw_datetime(dt), "20 Jun 2026, 9:05 AM")

    def test_none_renders_empty_string(self):
        self.assertEqual(tw_datetime(None), "")


@override_settings(TIME_ZONE="UTC", USE_TZ=True)
class TwDatetimeRenderTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(name="Globomantics", code="GMEC")
        self.admin = User.objects.create_user("admin_twdt", role="admin")
        self.client_user = User.objects.create_user(
            "client_twdt", role="client", client=self.org
        )

    def _make_ticket(self):
        return Ticket.objects.create(
            subject="Format sweep ticket", description="Body text here.",
            requester=self.client_user, client=self.org, status=Ticket.Status.NEW,
        )

    def test_admin_timeline_renders_tw_datetime(self):
        t = self._make_ticket()
        # Pin the submitted event's timestamp; the drawer renders it via tw_datetime.
        ev = t.events.filter(action="submitted").get()
        TicketEvent.objects.filter(pk=ev.pk).update(created_at=PINNED)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_ticket_timeline", args=[t.pk]))
        self.assertContains(resp, PINNED_STR)

    def test_client_ticket_detail_renders_tw_datetime(self):
        # A non-admin portal page: also proves its {% load ticket_labels %} is present,
        # since a missing load raises TemplateSyntaxError only when this page renders.
        t = self._make_ticket()
        Ticket.objects.filter(pk=t.pk).update(created_at=PINNED)
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("client_ticket_detail", args=[t.pk]))
        self.assertContains(resp, PINNED_STR)
