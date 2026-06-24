"""Email delivery layer on top of the in-app Notification feed.

A single entry point — ``email_for_notification`` — decides whether a given
``Notification`` should also be emailed and, if so, sends a plain-text message.
It is driven by the admin Settings toggles (``OrganisationSettings.notification_prefs``):

* The notification's ``action`` is mapped to a Settings **event key**.
* The recipient is classified into an **audience** by role:
    - ``admin``                 -> governed by the ``<event>_admin`` toggle
    - ``developer`` / ``tester``-> governed by the ``<event>_assignee`` toggle
    - ``client`` / ``subuser``  -> always emailed (their own ticket; no toggle)
* Actions with no mapped event are always emailed (the grid only governs its
  eight listed events for the admin/assignee audiences).

Sending is best-effort and wrapped by the caller in ``transaction.on_commit``,
so a mail outage never rolls back the ticket action that produced it.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

# Notification.action -> Settings event key (admin_portal.models.NOTIFICATION_EVENTS).
# Anything not listed here is treated as "always email" (no toggle governs it).
ACTION_TO_EVENT = {
    "new_ticket": "new_ticket",
    "assign": "assigned",
    "reassign": "reassigned",
    "submit_for_testing": "ready_for_test",
    "pass": "tester_verdict",
    "fail": "tester_verdict",
    "resume": "client_response",
    "close": "closed",
    "overdue": "overdue",
}

# recipient.role -> the audience suffix used in the prefs keys. Roles not listed
# (client / subuser) are always emailed.
ROLE_TO_AUDIENCE = {
    "admin": "admin",
    "developer": "assignee",
    "tester": "assignee",
}


def _is_enabled(action, role):
    """Consult the org Settings toggles for this action + recipient role.

    Returns True when the email should be sent. Client/sub-user recipients and
    unmapped actions are always enabled; admin/assignee audiences honour the
    per-event toggle (absent keys default to enabled).
    """
    audience = ROLE_TO_AUDIENCE.get(role)
    if audience is None:
        return True  # client / sub-user: always notified about their own ticket
    event = ACTION_TO_EVENT.get(action)
    if event is None:
        return True  # action not covered by the grid -> always email

    # Imported lazily to avoid an app-load import cycle.
    from admin_portal.models import OrganisationSettings

    prefs = OrganisationSettings.load().notification_prefs or {}
    return prefs.get(f"{event}_{audience}", True)


def _ticket_url(notification):
    """Absolute URL to the notification's ticket (best-effort)."""
    base = getattr(settings, "BASE_URL", "").rstrip("/")
    try:
        path = reverse("notification_open", args=[notification.pk])
    except NoReverseMatch:
        path = "/notifications/"
    return f"{base}{path}" if base else path


def email_for_notification(notification):
    """Send the email for a Notification if enabled. Best-effort; never raises."""
    recipient = notification.recipient
    if recipient is None or not recipient.email:
        return
    if not _is_enabled(notification.action, recipient.role):
        return

    ref = notification.ticket.reference if notification.ticket_id else "Tweedle"
    subject = f"[Tweedle] {ref}: update on your ticket"
    body = (
        f"Hi {recipient.get_short_name() or recipient.get_username()},\n\n"
        f"{notification.message}\n\n"
        f"View it here: {_ticket_url(notification)}\n\n"
        f"— Tweedle"
    )
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient.email],
            fail_silently=False,
        )
    except Exception:  # pragma: no cover - mail outages must not break the flow
        logger.exception("Failed to send notification email to %s", recipient.email)
