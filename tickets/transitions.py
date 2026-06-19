"""The guarded transition engine — the heart of Tweedle (TARGET §4, §5, §8).

Every ticket status/sub_status change MUST go through `transition()`. Views
never mutate `status` / `sub_status` directly. A single declarative registry
(`TRANSITIONS`) describes every legal move; `transition()` enforces role,
legal-state, required input and guards, then mutates state, writes one
immutable `TicketEvent`, and creates `Notification` rows — all in one atomic
transaction. Illegal or unauthorized attempts raise and change nothing.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification

from .models import Ticket, TicketEvent

User = get_user_model()

REOPEN_WINDOW_DAYS = getattr(settings, "REOPEN_WINDOW_DAYS", 14)

S = Ticket.Status
SS = Ticket.SubStatus

# Sentinels for the sub_status mutation mode (distinct from "set to None").
UNCHANGED = object()        # leave sub_status exactly as it is
RESTORE_PAUSED = object()   # restore from paused_sub_status (resume)


# ── Exceptions ──────────────────────────────────────────────────────────────
class TransitionError(Exception):
    """Base class for all transition failures."""


class TransitionNotAllowed(TransitionError):
    """The actor's role/ownership is not permitted to perform the action."""


class InvalidTransition(TransitionError):
    """The action is illegal from the ticket's current state, or a guard failed."""


class TransitionValidationError(TransitionError):
    """A required input field is missing."""


# ── Guards: (ticket, actor, data) -> None, or raise ─────────────────────────
def _require_requester_or_admin(ticket, actor):
    """Non-admin actors may only act on their own ticket."""
    if actor.role == "admin":
        return
    if actor.pk != ticket.requester_id:
        raise TransitionNotAllowed(
            f"{actor} is not the requester of {ticket.reference}."
        )


def _require_org_client_or_requester_or_admin(ticket, actor):
    """Admin, the ticket's requester, or the org's primary (client-role) account.

    Lets the org's client-role account holder act on a SUB-USER's ticket
    (TARGET §4/§6: the client/admin hold approval of a sub-user's ticket), while
    keeping cross-org clients and non-requester sub-users out. The role check in
    each Rule still gates which roles may attempt the action at all.
    """
    if actor.role == "admin":
        return
    if actor.pk == ticket.requester_id:
        return
    if actor.role == "client" and actor.client_id and actor.client_id == ticket.client_id:
        return
    raise TransitionNotAllowed(
        f"{actor} may not act on {ticket.reference}."
    )


def guard_cancel(ticket, actor, data):
    # §6 gives the client no cancel verb; T3 is requester/admin only.
    _require_requester_or_admin(ticket, actor)


def guard_approve(ticket, actor, data):
    _require_org_client_or_requester_or_admin(ticket, actor)


def guard_request_changes(ticket, actor, data):
    _require_org_client_or_requester_or_admin(ticket, actor)


def guard_confirm(ticket, actor, data):
    # A sub-user under the ticket's client may confirm.
    if actor.pk != ticket.requester_id and actor.client_id != ticket.client_id:
        raise TransitionNotAllowed(
            "Only a sub-user of this client may confirm the UAT build."
        )


def guard_reopen(ticket, actor, data):
    if actor.role == "admin":
        return  # admin may reopen resolved/closed anytime
    # Requester or the org's primary client may reopen (resolved unrestricted;
    # closed is window-bounded below for non-admins).
    _require_org_client_or_requester_or_admin(ticket, actor)
    if ticket.status == S.CLOSED:
        if ticket.closed_at is None:
            raise InvalidTransition("Closed ticket has no closed_at timestamp.")
        if timezone.now() - ticket.closed_at > timedelta(days=REOPEN_WINDOW_DAYS):
            raise InvalidTransition(
                "The client reopen window has passed; submit a related ticket."
            )


def guard_tester_assigned(ticket, actor, data):
    if not ticket.assigned_tester_id:
        raise InvalidTransition(
            "A tester must be assigned to route through testing."
        )


def guard_no_tester_assigned(ticket, actor, data):
    if ticket.assigned_tester_id:
        raise InvalidTransition(
            "mark_ready is unavailable once a tester is assigned; "
            "use submit_for_testing."
        )


def guard_reassign(ticket, actor, data):
    if not data.get("developer") and not data.get("tester"):
        raise TransitionValidationError(
            "reassign requires a new developer and/or tester."
        )


# ── Effects: (ticket, actor, data, from_status, from_sub) -> mutate, no save ─
def effects_assign(ticket, actor, data, from_status, from_sub):
    ticket.assigned_developer = data["developer"]
    if data.get("tester") is not None:
        ticket.assigned_tester = data.get("tester")


def effects_request_info(ticket, actor, data, from_status, from_sub):
    ticket.paused_sub_status = from_sub  # stash the internal stage; SLA pauses


def effects_resume(ticket, actor, data, from_status, from_sub):
    ticket.paused_sub_status = None  # already restored into sub_status


def effects_clear_subuser_confirmed(ticket, actor, data, from_status, from_sub):
    ticket.subuser_confirmed = False


def effects_approve(ticket, actor, data, from_status, from_sub):
    ticket.accepted_at = timezone.now()
    ticket.accepted_by = actor


def effects_close(ticket, actor, data, from_status, from_sub):
    ticket.closed_at = timezone.now()


def effects_confirm(ticket, actor, data, from_status, from_sub):
    ticket.subuser_confirmed = True


def effects_reassign(ticket, actor, data, from_status, from_sub):
    if data.get("developer") is not None:
        ticket.assigned_developer = data.get("developer")
    if data.get("tester") is not None:
        ticket.assigned_tester = data.get("tester")


# ── Notify resolvers: (ticket, actor, data) -> iterable[User] ───────────────
def _admins():
    return list(User.objects.filter(role="admin"))


def _developer(ticket):
    return [ticket.assigned_developer] if ticket.assigned_developer_id else []


def _tester(ticket):
    return [ticket.assigned_tester] if ticket.assigned_tester_id else []


def _assignees(ticket):
    return _developer(ticket) + _tester(ticket)


def _primary_client(ticket):
    if ticket.client_id:
        return list(User.objects.filter(client_id=ticket.client_id, role="client"))
    if ticket.requester.role == "client":
        return [ticket.requester]
    return []


notify_requester = lambda t, a, d: [t.requester]
notify_developer = lambda t, a, d: _developer(t)
notify_tester = lambda t, a, d: _tester(t)
notify_admins = lambda t, a, d: _admins()
notify_assignees = lambda t, a, d: _assignees(t)
notify_admins_and_assignees = lambda t, a, d: _admins() + _assignees(t)
notify_developer_and_admins = lambda t, a, d: _developer(t) + _admins()
notify_admins_and_developer = lambda t, a, d: _admins() + _developer(t)
notify_primary_client_and_admins = lambda t, a, d: _primary_client(t) + _admins()
notify_new_assignees = lambda t, a, d: [
    u for u in (d.get("developer"), d.get("tester")) if u is not None
]


# ── The Rule ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Rule:
    action: str
    from_status: frozenset
    allowed_roles: frozenset
    to_status: Optional[str] = None        # None = main status unchanged
    from_sub: Optional[frozenset] = None   # required current sub_status, if any
    to_sub_status: object = UNCHANGED      # str | None | UNCHANGED | RESTORE_PAUSED
    required_fields: tuple = ()
    guard: Optional[Callable] = None
    effects: Optional[Callable] = None
    notify: Optional[Callable] = None
    event_action: Optional[str] = None     # override the audited action name

    def check_role(self, actor):
        if actor.role not in self.allowed_roles:
            raise TransitionNotAllowed(
                f"Role '{actor.role}' may not perform '{self.action}'."
            )

    def check_legal(self, ticket):
        if ticket.status not in self.from_status:
            raise InvalidTransition(
                f"'{self.action}' is not legal from status '{ticket.status}'."
            )
        if self.from_sub is not None and ticket.sub_status not in self.from_sub:
            raise InvalidTransition(
                f"'{self.action}' is not legal from sub-status "
                f"'{ticket.sub_status}'."
            )

    def validate(self, data):
        for f in self.required_fields:
            if not data.get(f):
                raise TransitionValidationError(
                    f"'{self.action}' requires '{f}'."
                )


# ── The declarative registry: one entry per T1–T12, S1–S5, + confirm/reassign
REQUESTER_ROLES = frozenset({"client", "subuser"})

TRANSITIONS = {
    # ── Main transitions ────────────────────────────────────────────────
    "assign": Rule(  # T1
        action="assign",
        from_status=frozenset({S.NEW}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.IN_PROGRESS,
        to_sub_status=SS.DEVELOPMENT,
        required_fields=("developer",),
        effects=effects_assign,
        notify=notify_assignees,
    ),
    "reject": Rule(  # T2
        action="reject",
        from_status=frozenset({S.NEW}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.REJECTED,
        to_sub_status=None,
        required_fields=("reason",),
        notify=notify_requester,
    ),
    "cancel": Rule(  # T3
        action="cancel",
        from_status=frozenset({S.NEW, S.IN_PROGRESS, S.AWAITING_CLIENT}),
        allowed_roles=frozenset({"admin"}) | REQUESTER_ROLES,
        to_status=S.CANCELLED,
        to_sub_status=None,
        guard=guard_cancel,
        notify=notify_requester,
    ),
    "request_info": Rule(  # T4
        action="request_info",
        from_status=frozenset({S.IN_PROGRESS}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.AWAITING_CLIENT,
        to_sub_status=None,
        required_fields=("message",),
        effects=effects_request_info,
        notify=notify_requester,
    ),
    "resume": Rule(  # T5
        action="resume",
        from_status=frozenset({S.AWAITING_CLIENT}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.IN_PROGRESS,
        to_sub_status=RESTORE_PAUSED,
        effects=effects_resume,
        notify=notify_developer,
    ),
    "send_to_uat": Rule(  # T6
        action="send_to_uat",
        from_status=frozenset({S.IN_PROGRESS}),
        from_sub=frozenset({SS.READY_FOR_UAT}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.UAT,
        to_sub_status=None,
        effects=effects_clear_subuser_confirmed,
        notify=notify_requester,
    ),
    "approve": Rule(  # T7
        action="approve",
        from_status=frozenset({S.UAT}),
        allowed_roles=frozenset({"client", "admin"}),
        to_status=S.RESOLVED,
        to_sub_status=None,
        guard=guard_approve,
        effects=effects_approve,
        notify=notify_admins_and_assignees,
    ),
    "request_changes": Rule(  # T8
        action="request_changes",
        from_status=frozenset({S.UAT}),
        allowed_roles=frozenset({"client", "subuser", "admin"}),
        to_status=S.IN_PROGRESS,
        to_sub_status=SS.DEVELOPMENT,
        required_fields=("feedback",),
        guard=guard_request_changes,
        effects=effects_clear_subuser_confirmed,
        notify=notify_admins_and_developer,
    ),
    "close": Rule(  # T9
        action="close",
        from_status=frozenset({S.RESOLVED}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.CLOSED,
        to_sub_status=None,
        effects=effects_close,
        notify=notify_requester,
    ),
    "reopen": Rule(  # T10 + T11 (merged; guard enforces the window)
        action="reopen",
        from_status=frozenset({S.RESOLVED, S.CLOSED}),
        allowed_roles=frozenset({"client", "admin"}),
        to_status=S.IN_PROGRESS,
        to_sub_status=SS.DEVELOPMENT,
        required_fields=("reason",),
        guard=guard_reopen,
        notify=notify_admins_and_developer,
    ),
    "restore": Rule(  # T12
        action="restore",
        from_status=frozenset({S.REJECTED}),
        allowed_roles=frozenset({"admin"}),
        to_status=S.NEW,
        to_sub_status=None,
        notify=None,
    ),
    "confirm": Rule(  # sub-user UAT signal (not a status change)
        action="confirm",
        from_status=frozenset({S.UAT}),
        allowed_roles=frozenset({"subuser"}),
        to_status=None,
        to_sub_status=UNCHANGED,
        guard=guard_confirm,
        effects=effects_confirm,
        notify=notify_primary_client_and_admins,
    ),
    "reassign": Rule(  # TARGET §5 reassignment (not a status change)
        action="reassign",
        from_status=frozenset({S.IN_PROGRESS, S.AWAITING_CLIENT}),
        allowed_roles=frozenset({"admin"}),
        to_status=None,
        to_sub_status=UNCHANGED,
        guard=guard_reassign,
        effects=effects_reassign,
        notify=notify_new_assignees,
        event_action="reassigned",
    ),
    # ── Sub-transitions (status stays in_progress) ──────────────────────
    "submit_for_testing": Rule(  # S1
        action="submit_for_testing",
        from_status=frozenset({S.IN_PROGRESS}),
        from_sub=frozenset({SS.DEVELOPMENT}),
        allowed_roles=frozenset({"developer"}),
        to_sub_status=SS.TESTING,
        guard=guard_tester_assigned,
        notify=notify_tester,
    ),
    "pass": Rule(  # S2
        action="pass",
        from_status=frozenset({S.IN_PROGRESS}),
        from_sub=frozenset({SS.TESTING}),
        allowed_roles=frozenset({"tester"}),
        to_sub_status=SS.READY_FOR_UAT,
        notify=notify_admins,
    ),
    "fail": Rule(  # S3
        action="fail",
        from_status=frozenset({S.IN_PROGRESS}),
        from_sub=frozenset({SS.TESTING}),
        allowed_roles=frozenset({"tester"}),
        to_sub_status=SS.RETURNED,
        required_fields=("failure_notes",),
        notify=notify_developer,
    ),
    "resubmit_for_testing": Rule(  # S4
        action="resubmit_for_testing",
        from_status=frozenset({S.IN_PROGRESS}),
        from_sub=frozenset({SS.RETURNED}),
        allowed_roles=frozenset({"developer"}),
        to_sub_status=SS.TESTING,
        guard=guard_tester_assigned,
        notify=notify_tester,
    ),
    "mark_ready": Rule(  # S5
        action="mark_ready",
        from_status=frozenset({S.IN_PROGRESS}),
        from_sub=frozenset({SS.DEVELOPMENT}),
        allowed_roles=frozenset({"developer"}),
        to_sub_status=SS.READY_FOR_UAT,
        guard=guard_no_tester_assigned,
        notify=notify_admins,
    ),
}


# ── Helpers ─────────────────────────────────────────────────────────────────
_NOTE_FIELDS = ("reason", "message", "feedback", "failure_notes", "note")


def _extract_note(data):
    for f in _NOTE_FIELDS:
        if data.get(f):
            return str(data[f])
    return ""


def _message_for(rule, ticket, actor):
    label = rule.event_action or rule.action
    return f"{ticket.reference}: '{label}' by {actor.get_username()}"


# ── Object-level ownership check ────────────────────────────────────────────
def _check_ownership(ticket, actor):
    """Raise TransitionNotAllowed if actor has no object-level access to ticket.

    Called after the role check (which verifies the role type is allowed) and
    before the legal-state check.  Admin is unrestricted.  Developer/tester
    must be the assigned assignee.  Client/subuser must belong to the ticket's
    client org (org-level, not requester-only — guard callables enforce the
    finer requester restriction where needed).
    """
    role = actor.role
    if role == "admin":
        return
    if role == "developer":
        if ticket.assigned_developer_id != actor.pk:
            raise TransitionNotAllowed(
                f"Developer '{actor}' is not assigned to {ticket.reference}."
            )
    elif role == "tester":
        if ticket.assigned_tester_id != actor.pk:
            raise TransitionNotAllowed(
                f"Tester '{actor}' is not assigned to {ticket.reference}."
            )
    elif role in ("client", "subuser"):
        if ticket.client_id != actor.client_id:
            raise TransitionNotAllowed(
                f"'{actor}' does not belong to the client org for {ticket.reference}."
            )


# ── The one service every view calls ────────────────────────────────────────
def transition(ticket, action, actor, **data):
    """Perform `action` on `ticket` as `actor`, atomically and guarded.

    On success: mutates state, writes exactly one TicketEvent, and creates
    Notification rows for the mapped recipients. On any failure raises a
    TransitionError subclass and changes nothing.
    """
    try:
        rule = TRANSITIONS[action]
    except KeyError:
        raise InvalidTransition(f"Unknown action '{action}'.")

    # All checks run BEFORE the atomic block, so a failure changes nothing.
    rule.check_role(actor)
    _check_ownership(ticket, actor)
    rule.check_legal(ticket)
    rule.validate(data)
    if rule.guard:
        rule.guard(ticket, actor, data)

    from_status = ticket.status
    from_sub = ticket.sub_status

    # Resolve the target state up-front.
    new_status = rule.to_status if rule.to_status is not None else ticket.status
    if rule.to_sub_status is UNCHANGED:
        new_sub = ticket.sub_status
    elif rule.to_sub_status is RESTORE_PAUSED:
        new_sub = ticket.paused_sub_status or SS.DEVELOPMENT
    else:
        new_sub = rule.to_sub_status  # a concrete value or None

    with transaction.atomic():
        # Set status + sub_status together and save ONCE so the DB
        # CheckConstraint never sees an inconsistent intermediate row.
        ticket.status = new_status
        ticket.sub_status = new_sub
        if rule.effects:
            rule.effects(ticket, actor, data, from_status, from_sub)
        ticket.save()

        TicketEvent.objects.create(
            ticket=ticket,
            actor=actor,
            action=rule.event_action or rule.action,
            from_status=from_status or "",
            from_sub_status=from_sub,
            to_status=ticket.status or "",
            to_sub_status=ticket.sub_status,
            note=_extract_note(data),
        )

        if rule.notify:
            seen = set()
            for user in rule.notify(ticket, actor, data):
                if user is None or user.pk == actor.pk or user.pk in seen:
                    continue
                seen.add(user.pk)
                Notification.objects.create(
                    recipient=user,
                    ticket=ticket,
                    actor=actor,
                    action=rule.event_action or rule.action,
                    message=_message_for(rule, ticket, actor),
                )

    return ticket
