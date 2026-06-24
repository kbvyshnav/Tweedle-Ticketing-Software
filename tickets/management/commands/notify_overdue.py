"""Send overdue-SLA warnings for tickets past their resolution due date (TARGET §9).

A ticket whose pause-aware SLA clock (tickets/sla.py) has run out while work is
still on us (status new/in_progress) is overdue. This command notifies the
internal team — the assigned developer, assigned tester, and all admins — once
per breach, then marks the ticket so it isn't warned again until the clock is
reset/extended (resume/reopen flips overdue_notified back off).

These notifications carry action="overdue", so the email layer
(notifications/email.py) routes them through the Settings "overdue" toggles
(overdue_admin / overdue_assignee). The client is deliberately NOT warned — an
SLA breach is an internal matter.

Run on a schedule (cron / Windows Task Scheduler):
    python manage.py notify_overdue
    python manage.py notify_overdue --dry-run

Idempotent: overdue_notified guards against re-warning every run.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from notifications.models import Notification
from tickets import sla
from tickets.models import Ticket

User = get_user_model()


class Command(BaseCommand):
    help = "Notify the internal team about tickets that have breached their SLA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be warned without creating notifications.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        admins = list(User.objects.filter(role="admin"))

        warned = 0
        candidates = Ticket.objects.filter(
            status__in=sla.RUNNING_STATUSES, overdue_notified=False
        ).select_related("assigned_developer", "assigned_tester")

        for ticket in candidates:
            if not ticket.is_overdue:
                continue
            if dry_run:
                self.stdout.write(f"[dry-run] would warn for {ticket.reference}")
                warned += 1
                continue
            with transaction.atomic():
                self._warn(ticket, admins)
                ticket.overdue_notified = True
                ticket.save(update_fields=["overdue_notified"])
            warned += 1

        verb = "Would warn" if dry_run else "Warned"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} on {warned} overdue ticket(s)."
        ))

    @staticmethod
    def _warn(ticket, admins):
        """Create one overdue Notification per internal recipient (deduped)."""
        recipients = []
        if ticket.assigned_developer_id:
            recipients.append(ticket.assigned_developer)
        if ticket.assigned_tester_id:
            recipients.append(ticket.assigned_tester)
        recipients.extend(admins)

        seen = set()
        for user in recipients:
            if user is None or user.pk in seen:
                continue
            seen.add(user.pk)
            Notification.objects.create(
                recipient=user,
                ticket=ticket,
                actor=None,
                action="overdue",
                message=f"{ticket.reference}: overdue — past its resolution due date.",
            )
