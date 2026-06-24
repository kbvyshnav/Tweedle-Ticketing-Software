"""Auto-close resolved tickets the client has left untouched (TARGET §9).

A ticket sits in `resolved` after the client accepts the fix; if no one acts on
it for `AUTO_CLOSE_DAYS`, this command closes it (resolved -> closed) through the
guarded transition() engine, so it gets the normal audit event + "ticket closed"
notification. "Stale" is measured from the most recent event that moved the
ticket into `resolved` (the same resolution-time source the Reports page uses).

Run on a schedule (cron / Windows Task Scheduler):
    python manage.py close_stale_resolved              # close everything stale
    python manage.py close_stale_resolved --days 14    # override the window
    python manage.py close_stale_resolved --dry-run     # report only, change nothing

Idempotent: a closed ticket leaves the `resolved` set, so re-runs skip it.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from tickets.models import Ticket
from tickets.transitions import TransitionError, transition

User = get_user_model()
S = Ticket.Status


class Command(BaseCommand):
    help = "Close resolved tickets with no client action after AUTO_CLOSE_DAYS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Override AUTO_CLOSE_DAYS (the staleness window in days).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be closed without changing anything.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = getattr(settings, "AUTO_CLOSE_DAYS", 7)
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        actor = self._system_actor()
        if actor is None and not dry_run:
            self.stderr.write(self.style.ERROR(
                "No admin/superuser found to act as the closer — aborting."
            ))
            return

        closed = 0
        skipped = 0
        for ticket in Ticket.objects.filter(status=S.RESOLVED):
            resolved_at = self._resolved_at(ticket)
            if resolved_at is None or resolved_at > cutoff:
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(
                    f"[dry-run] would close {ticket.reference} "
                    f"(resolved {resolved_at:%Y-%m-%d})"
                )
                closed += 1
                continue
            try:
                transition(ticket, "close", actor=actor)
                closed += 1
            except TransitionError as exc:
                skipped += 1
                self.stderr.write(self.style.WARNING(
                    f"Skipped {ticket.reference}: {exc}"
                ))

        verb = "Would close" if dry_run else "Closed"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {closed} stale resolved ticket(s) "
            f"(> {days} days); skipped {skipped}."
        ))

    @staticmethod
    def _resolved_at(ticket):
        """When the ticket most recently entered `resolved` (or None)."""
        ev = (
            ticket.events.filter(to_status=S.RESOLVED)
            .order_by("-created_at", "-id")
            .first()
        )
        return ev.created_at if ev else None

    @staticmethod
    def _system_actor():
        """An admin to attribute the auto-close to (the engine requires role=admin;
        a superuser whose role isn't admin would fail that check, so we only pick
        role=admin users, preferring a superuser among them)."""
        return (
            User.objects.filter(is_superuser=True, role="admin").first()
            or User.objects.filter(role="admin").first()
        )
