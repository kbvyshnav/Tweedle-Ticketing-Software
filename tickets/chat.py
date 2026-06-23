"""Ticket chat (TicketMessage) posting — the one place a message is created.

Mirrors the spirit of the transition engine: a single guarded helper that every
portal's message-post view calls. Views still enforce object-level ownership
(who may see the ticket); this helper enforces the message-level rules (non-empty
body, ticket not in a locked/terminal state). Display stays read-only in the
templates; this adds the write path (Level 1: plain form-POST, no live socket).
"""

from django.contrib.auth import get_user_model

from notifications.models import Notification

from .models import Ticket, TicketMessage

User = get_user_model()

# Chat is closed once a ticket reaches a terminal state — no new replies.
CHAT_LOCKED_STATUSES = frozenset(
    {Ticket.Status.CLOSED, Ticket.Status.REJECTED, Ticket.Status.CANCELLED}
)


class ChatError(Exception):
    """Raised when a chat message cannot be posted (empty / locked ticket)."""


def _notify_message_recipients(ticket, author):
    """Notify the other ticket participants (requester, assignees, admins) of a
    new chat message — never the author. Mirrors the engine's notify dedupe."""
    candidates = []
    if ticket.requester_id:
        candidates.append(ticket.requester)
    if ticket.assigned_developer_id:
        candidates.append(ticket.assigned_developer)
    if ticket.assigned_tester_id:
        candidates.append(ticket.assigned_tester)
    candidates.extend(User.objects.filter(role="admin"))

    seen = set()
    for user in candidates:
        if user is None or user.pk == author.pk or user.pk in seen:
            continue
        seen.add(user.pk)
        Notification.objects.create(
            recipient=user,
            ticket=ticket,
            actor=author,
            action="message",
            message=f"{ticket.reference}: new message from {author.get_username()}",
        )


def post_ticket_message(ticket, author, body):
    """Create one TicketMessage after validating it. Raises ChatError on failure.

    The caller is responsible for object-level access (it has already fetched the
    ticket scoped to the requesting user). This only validates the message itself.
    """
    body = (body or "").strip()
    if not body:
        raise ChatError("Message cannot be empty.")
    if ticket.status in CHAT_LOCKED_STATUSES:
        raise ChatError("This ticket is closed — no new messages can be posted.")
    message = TicketMessage.objects.create(ticket=ticket, author=author, body=body)
    _notify_message_recipients(ticket, author)
    return message


def post_info_request(ticket, author, body):
    """Record an admin `request_info` message as a highlighted chat message.

    Called after a successful `request_info` transition so the client/sub-user can
    actually SEE what information the admin asked for (the transition alone only
    flips status + writes the audit note). Returns None for an empty body.
    """
    body = (body or "").strip()
    if not body:
        return None
    return TicketMessage.objects.create(
        ticket=ticket,
        author=author,
        body=body,
        kind=TicketMessage.Kind.INFO_REQUEST,
    )
