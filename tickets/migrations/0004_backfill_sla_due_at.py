"""Backfill sla_due_at for tickets created before the resolution-SLA clock.

Sets each existing ticket's deadline to created_at + the per-priority target,
matching tickets/sla.py (constants inlined so this migration stays frozen).
Open paused tickets (awaiting_client/uat) just get the baseline deadline; their
sla_paused_at stays null, which is harmless for the overdue calculation.
"""

from datetime import timedelta

from django.db import migrations

# Mirror of tickets.sla.RESOLUTION_TARGET_DAYS at the time of writing.
TARGET_DAYS = {"high": 3, "medium": 5, "low": 7}
DEFAULT_TARGET_DAYS = 5


def backfill(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    for ticket in Ticket.objects.filter(sla_due_at__isnull=True).iterator():
        days = TARGET_DAYS.get(ticket.priority, DEFAULT_TARGET_DAYS)
        Ticket.objects.filter(pk=ticket.pk).update(
            sla_due_at=ticket.created_at + timedelta(days=days)
        )


def noop(apps, schema_editor):
    # Reversible: the field simply goes back to null on rollback (handled by the
    # schema migration), so nothing to undo here.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0003_ticket_sla_due_at_ticket_sla_paused_at"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
