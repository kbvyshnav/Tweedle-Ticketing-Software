import os

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Ticket(models.Model):
    """The single source of truth for a support ticket (TARGET §3, §8).

    `status` is the lifecycle the requester sees; `sub_status` is the internal
    work stage and is non-null **iff** `status == in_progress` (enforced by a
    DB CheckConstraint below and maintained by the transition() engine).
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In Progress"
        AWAITING_CLIENT = "awaiting_client", "Awaiting Client"
        UAT = "uat", "UAT"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class SubStatus(models.TextChoices):
        DEVELOPMENT = "development", "Development"
        TESTING = "testing", "Testing"
        RETURNED = "returned", "Returned"
        READY_FOR_UAT = "ready_for_uat", "Ready for UAT"

    class Priority(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    # Human-readable key: <CLIENT_CODE><YY><MM><NNNN> (e.g. GMEC25010001).
    reference = models.CharField(max_length=20, unique=True, blank=True)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, blank=True)
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM
    )

    requester = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="requested_tickets"
    )
    client = models.ForeignKey(
        "accounts.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    assigned_developer = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dev_tickets",
    )
    assigned_tester = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="test_tickets",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW
    )
    sub_status = models.CharField(
        max_length=20, choices=SubStatus.choices, null=True, blank=True
    )
    paused_sub_status = models.CharField(
        max_length=20, choices=SubStatus.choices, null=True, blank=True
    )
    subuser_confirmed = models.BooleanField(default=False)

    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_tickets",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    # Resolution-time SLA (see tickets/sla.py). `sla_due_at` is the deadline,
    # pushed forward by any time the clock spends paused (awaiting_client/uat);
    # `sla_paused_at` records when the current pause began (null when running).
    sla_due_at = models.DateTimeField(null=True, blank=True)
    sla_paused_at = models.DateTimeField(null=True, blank=True)

    linked_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_tickets",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # sub_status is non-null IFF status == in_progress (TARGET §3).
            models.CheckConstraint(
                name="ticket_sub_status_iff_in_progress",
                condition=(
                    Q(status="in_progress", sub_status__isnull=False)
                    | (~Q(status="in_progress") & Q(sub_status__isnull=True))
                ),
            ),
        ]

    def __str__(self):
        return f"{self.reference or '(unsaved)'} — {self.subject}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if not self.reference:
            self.reference = self._generate_reference()
        if is_new and self.sla_due_at is None:
            # Start the resolution SLA clock at creation; pauses/resets are
            # applied later by the transition() engine (see tickets/sla.py).
            from . import sla
            self.sla_due_at = timezone.now() + sla.target_delta(self.priority)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        """Resolution SLA breached and the clock is still running (tickets/sla.py)."""
        from . import sla
        return sla.is_overdue(self)

    def _generate_reference(self):
        """Build <CLIENT_CODE><YY><MM><NNNN>, sequence per client per month.

        NOTE: the per-month sequence has a minor concurrency race; the unique
        constraint on `reference` catches collisions. Fine for now.
        """
        code = self.client.code if self.client_id else "TWDL"
        now = timezone.now()
        prefix = f"{code}{now:%y%m}"
        last = (
            Ticket.objects.filter(reference__startswith=prefix)
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        seq = int(last[len(prefix):]) + 1 if last else 1
        return f"{prefix}{seq:04d}"


class TicketEvent(models.Model):
    """Immutable audit row, one per transition (TARGET §7). Never edited."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="events"
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_events",
    )
    action = models.CharField(max_length=40)
    from_status = models.CharField(max_length=20, blank=True)
    from_sub_status = models.CharField(max_length=20, null=True, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    to_sub_status = models.CharField(max_length=20, null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.ticket.reference}: {self.action}"


class TicketMessage(models.Model):
    """Chat message on a ticket.

    `kind` distinguishes an ordinary chat reply from an admin **information
    request** (the message attached to a `request_info` transition), so portals
    can highlight the latter prominently for the client/sub-user.
    """

    class Kind(models.TextChoices):
        MESSAGE = "message", "Message"
        INFO_REQUEST = "info_request", "Information Request"

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="messages"
    )
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ticket_messages"
    )
    body = models.TextField()
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.MESSAGE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class TicketAttachment(models.Model):
    """File attached to a ticket (stub for Phase 2)."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="attachments"
    )
    uploaded_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ticket_attachments"
    )
    file = models.FileField(upload_to="ticket_attachments/")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        """Just the file's base name (no upload path) for display/download."""
        return os.path.basename(self.file.name) if self.file else ""
