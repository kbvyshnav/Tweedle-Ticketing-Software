"""Backfill the creation-time "submitted" timeline event onto pre-signal tickets.

Tickets created before the record_submission_event signal existed (tickets/signals.py)
have no "submitted" TicketEvent, so their timeline doesn't start at "Ticket Submitted".
This command creates a BYTE-IDENTICAL event for each such ticket — same seven fields
the signal sets — and backdates it to the ticket's creation time so it sorts first.

Usage:
    python manage.py backfill_submitted_events   # idempotent: re-running backfills 0

This is a CREATION-time audit entry, mirroring the signal: it does NOT go through the
guarded transition() engine (no status mutation, no second audit row). The idempotency
filter (exclude tickets that already have a submitted event) means re-running is a no-op.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from tickets.models import Ticket, TicketEvent


class Command(BaseCommand):
    help = "Backfill the creation-time 'submitted' event onto tickets that lack one."

    @transaction.atomic
    def handle(self, *args, **options):
        backfilled = 0
        for ticket in Ticket.objects.exclude(events__action="submitted"):
            ev = TicketEvent.objects.create(
                ticket=ticket,
                actor=ticket.requester,
                action="submitted",
                from_status="",
                from_sub_status=None,
                to_status="new",
                to_sub_status=None,
                note="",
            )
            # Bypass auto_now_add so the event sorts first (Meta.ordering = created_at, id).
            TicketEvent.objects.filter(pk=ev.pk).update(created_at=ticket.created_at)
            backfilled += 1

        skipped = Ticket.objects.count() - backfilled
        self.stdout.write(self.style.SUCCESS(
            f"Backfilled {backfilled} tickets, "
            f"skipped {skipped} that already had a submission event."
        ))
