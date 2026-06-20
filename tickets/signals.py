"""Ticket signals.

Records a creation-time audit entry so every ticket's timeline starts with a
real "Ticket Submitted" event (TARGET §7 — the audit trail is the timeline every
portal renders). This is a CREATION event, not a status transition: it never
goes through the guarded transition() engine, and it fires only on genuine
creation, so transitions (incl. restore: rejected→new) never add a second one.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ticket, TicketEvent


@receiver(post_save, sender=Ticket, dispatch_uid="tickets.record_submission_event")
def record_submission_event(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    TicketEvent.objects.create(
        ticket=instance,
        actor=instance.requester,
        action="submitted",
        from_status="",
        from_sub_status=None,
        to_status="new",
        to_sub_status=None,
        note="",
    )
