"""Tests for ticket attachments — upload on submit, validation, and display.

Covers the shared `tickets/attachments.py` field/helper plus the client and
sub-user submit flows and the detail-page display.
"""

import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Client
from tickets.attachments import save_attachments
from tickets.models import Ticket, TicketAttachment

User = get_user_model()
S = Ticket.Status

# Isolate uploads to a throwaway dir so tests never touch real MEDIA_ROOT.
_MEDIA = tempfile.mkdtemp(prefix="tweedle_test_media_")


def _pdf(name="spec.pdf", content=b"%PDF-1.4 test"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@override_settings(MEDIA_ROOT=_MEDIA)
class AttachmentUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.org = Client.objects.create(name="Acme Corp", code="ACME")
        self.client_user = User.objects.create_user(
            "client_main", email="cm@test.local", password="pw",
            role="client", client=self.org,
        )
        self.subuser = User.objects.create_user(
            "sub_main", email="sm@test.local", password="pw",
            role="subuser", client=self.org,
        )

    def _submit_payload(self, **extra):
        data = {
            "subject": "Export is empty",
            "description": "When I export the report the file is empty.",
            "category": "Bug",
            "priority": "medium",
        }
        data.update(extra)
        return data

    # ── Client submit ────────────────────────────────────────────────────────

    def test_client_submit_saves_attachment(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse("client_submit_ticket"),
            self._submit_payload(attachments=_pdf()),
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket = Ticket.objects.get(subject="Export is empty")
        self.assertEqual(ticket.attachments.count(), 1)
        att = ticket.attachments.first()
        self.assertEqual(att.uploaded_by, self.client_user)
        self.assertTrue(att.filename.endswith(".pdf"))

    def test_client_submit_without_attachment_still_works(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse("client_submit_ticket"), self._submit_payload())
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket = Ticket.objects.get(subject="Export is empty")
        self.assertEqual(ticket.attachments.count(), 0)

    def test_client_submit_multiple_attachments(self):
        self.client.force_login(self.client_user)
        resp = self.client.post(
            reverse("client_submit_ticket"),
            self._submit_payload(attachments=[_pdf("a.pdf"), _pdf("b.png")]),
        )
        self.assertRedirects(resp, reverse("client_dashboard"))
        ticket = Ticket.objects.get(subject="Export is empty")
        self.assertEqual(ticket.attachments.count(), 2)

    # ── Validation ───────────────────────────────────────────────────────────

    def test_disallowed_extension_rejected(self):
        self.client.force_login(self.client_user)
        bad = SimpleUploadedFile("evil.exe", b"MZ", content_type="application/octet-stream")
        resp = self.client.post(
            reverse("client_submit_ticket"),
            self._submit_payload(attachments=bad),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Ticket.objects.filter(subject="Export is empty").exists())
        self.assertContains(resp, "not an allowed file type")

    def test_too_many_files_rejected(self):
        self.client.force_login(self.client_user)
        files = [_pdf(f"f{i}.pdf") for i in range(4)]
        resp = self.client.post(
            reverse("client_submit_ticket"),
            self._submit_payload(attachments=files),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Ticket.objects.filter(subject="Export is empty").exists())
        self.assertContains(resp, "at most 3 files")

    @mock.patch("tickets.attachments.MAX_ATTACHMENT_SIZE", 10)
    def test_oversize_file_rejected(self):
        self.client.force_login(self.client_user)
        big = _pdf("big.pdf", content=b"x" * 50)  # > patched 10-byte cap
        resp = self.client.post(
            reverse("client_submit_ticket"),
            self._submit_payload(attachments=big),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Ticket.objects.filter(subject="Export is empty").exists())
        self.assertContains(resp, "larger than 10 MB")

    # ── Sub-user submit ──────────────────────────────────────────────────────

    def test_subuser_submit_saves_attachment(self):
        self.client.force_login(self.subuser)
        resp = self.client.post(
            reverse("subuser:submit_ticket"),
            self._submit_payload(attachments=_pdf()),
        )
        self.assertRedirects(resp, reverse("subuser:dashboard"))
        ticket = Ticket.objects.get(subject="Export is empty")
        self.assertEqual(ticket.attachments.count(), 1)
        self.assertEqual(ticket.attachments.first().uploaded_by, self.subuser)

    # ── Display ──────────────────────────────────────────────────────────────

    def test_attachment_shows_on_client_detail(self):
        self.client.force_login(self.client_user)
        ticket = Ticket.objects.create(
            subject="With file", description="desc here for testing length.",
            requester=self.client_user, client=self.org, status=S.NEW,
        )
        save_attachments(ticket, [_pdf("report.pdf")], self.client_user)
        resp = self.client.get(reverse("client_ticket_detail", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "report.pdf")
        self.assertContains(resp, "Download")


class AttachmentModelTests(TestCase):
    def test_filename_property_strips_path(self):
        att = TicketAttachment()
        att.file = "ticket_attachments/report.pdf"
        self.assertEqual(att.filename, "report.pdf")

    def test_filename_empty_when_no_file(self):
        # A fresh attachment has an empty (falsy) FileField.
        self.assertEqual(TicketAttachment().filename, "")
