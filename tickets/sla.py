"""Resolution-time SLA: due dates, overdue, and the pause-aware clock.

Single source of truth for the per-priority resolution targets and the rules
that decide when a ticket's SLA clock runs, pauses, or resets:

* The clock **runs** while work is on the support org (``new``, ``in_progress``).
* It **pauses** while we wait on the client (``awaiting_client``, ``uat``).
* It **resets** to a fresh deadline when a finished ticket is reopened/restored.
* A **paused** ticket is never "overdue" — we are not the blocker.

Deliberately model-light: the only stored state is ``Ticket.sla_due_at`` (the
deadline, pushed forward by any time spent paused) and ``Ticket.sla_paused_at``
(when the current pause began). Everything else is derived here. The SLA clock
is *started* in ``Ticket.save()`` on creation and *adjusted* by the transition()
engine via ``apply_clock`` — views never touch these fields directly.
"""

from datetime import timedelta

from django.utils import timezone

from .models import Ticket

S = Ticket.Status

# Resolution targets in days, by priority. These are also the values the admin
# Reports page uses for its TAT met/missed flag (admin_portal imports from here,
# so the two never drift).
RESOLUTION_TARGET_DAYS = {
    Ticket.Priority.HIGH: 3,
    Ticket.Priority.MEDIUM: 5,
    Ticket.Priority.LOW: 7,
}
DEFAULT_TARGET_DAYS = 5

# Statuses where the SLA clock is actively ticking (work is on the support org).
RUNNING_STATUSES = frozenset({S.NEW, S.IN_PROGRESS})
# Statuses where the clock is paused (waiting on the client).
PAUSED_STATUSES = frozenset({S.AWAITING_CLIENT, S.UAT})
# Statuses where the ticket is finished — the clock no longer runs.
TERMINAL_STATUSES = frozenset({S.RESOLVED, S.CLOSED, S.REJECTED, S.CANCELLED})


def target_days(priority):
    """Resolution target (days) for a priority, defaulting to medium's."""
    return RESOLUTION_TARGET_DAYS.get(priority, DEFAULT_TARGET_DAYS)


def target_delta(priority):
    return timedelta(days=target_days(priority))


def is_overdue(ticket, *, now=None):
    """True iff the clock is running, a deadline is set, and it has passed.

    Paused (awaiting_client/uat) and terminal tickets are never overdue.
    """
    if ticket.status not in RUNNING_STATUSES:
        return False
    if not ticket.sla_due_at:
        return False
    return (now or timezone.now()) > ticket.sla_due_at


def apply_clock(ticket, from_status, to_status, *, now=None):
    """Adjust the SLA clock fields in-place for a status change (no save).

    Called by transition() with the status before/after the move. Handles:
      * finished -> running (reopen/restore): start a fresh deadline from now.
      * running  -> paused: stamp when the pause began.
      * paused   -> running: extend the deadline by the paused duration.
    Every other move leaves the clock untouched (e.g. new -> in_progress keeps
    the original deadline running; in_progress sub-status changes don't matter).
    """
    now = now or timezone.now()
    if from_status in TERMINAL_STATUSES and to_status in RUNNING_STATUSES:
        ticket.sla_due_at = now + target_delta(ticket.priority)
        ticket.sla_paused_at = None
        ticket.overdue_notified = False  # fresh deadline -> may warn again
    elif from_status in RUNNING_STATUSES and to_status in PAUSED_STATUSES:
        ticket.sla_paused_at = now
    elif from_status in PAUSED_STATUSES and to_status in RUNNING_STATUSES:
        if ticket.sla_paused_at:
            ticket.sla_due_at = (ticket.sla_due_at or now) + (now - ticket.sla_paused_at)
        ticket.sla_paused_at = None
        ticket.overdue_notified = False  # deadline extended -> may warn again
