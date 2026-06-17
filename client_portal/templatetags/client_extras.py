"""Client-portal display helpers (TARGET §6 client column)."""

from django import template
from django.utils.html import format_html

from tickets.templatetags.shared_ticket_extras import (
    event_dot_cls as _event_dot_cls,
    event_icon as _event_icon,
    event_label as _event_label,
)

register = template.Library()

# key: (status, sub_status_or_None) -> (client label, CSS modifier)
# Sub-status detail hidden from clients — all in_progress stages show "In Progress".
CLIENT_TICKET_BADGES = {
    ("new", None): ("New", "new"),
    ("in_progress", "development"): ("In Progress", "progress"),
    ("in_progress", "testing"): ("In Progress", "progress"),
    ("in_progress", "returned"): ("In Progress", "progress"),
    ("in_progress", "ready_for_uat"): ("In Progress", "progress"),
    ("awaiting_client", None): ("Your Input Needed", "forwarded"),
    ("uat", None): ("UAT Approval", "uat"),
    ("resolved", None): ("Resolved", "resolved"),
    ("closed", None): ("Closed", "closed"),
    ("rejected", None): ("Rejected", "rejected"),
    ("cancelled", None): ("Cancelled", "rejected"),
}


@register.simple_tag
def client_ticket_badge(ticket):
    """Render the client-facing status badge for a ticket."""
    sub = ticket.sub_status if ticket.status == "in_progress" else None
    label, css = CLIENT_TICKET_BADGES.get(
        (ticket.status, sub), (ticket.get_status_display(), ticket.status)
    )
    return format_html(
        '<span class="tw-status-badge tw-status-badge--{}">{}</span>', css, label
    )


# ── Timeline event helpers — data lives in shared_ticket_extras ──────────────

register.filter("event_label", _event_label)
register.filter("event_dot_cls", _event_dot_cls)
register.filter("event_icon", _event_icon)
