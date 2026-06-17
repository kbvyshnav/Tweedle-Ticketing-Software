"""Developer-portal display helpers (TARGET §6 developer column)."""

from django import template
from django.utils.html import format_html

from tickets.templatetags.shared_ticket_extras import (
    event_dot_cls as _event_dot_cls,
    event_icon as _event_icon,
    event_label as _event_label,
)

register = template.Library()

# key: (status, sub_status_or_None) -> (dev label, CSS modifier, title|"")
# Developer column of TARGET_TICKET_FLOW.md §6.
DEV_TICKET_BADGES = {
    ("new", None):                    ("New",               "new",            ""),
    ("in_progress", "development"):   ("Development",       "development",    ""),
    ("in_progress", "testing"):       ("In Testing",        "testing",        ""),
    ("in_progress", "returned"):      ("Returned from QA",  "returned",       "Returned from Testing"),
    ("in_progress", "ready_for_uat"): ("Ready for UAT",     "testing-passed", "Testing Passed — Ready for UAT"),
    ("awaiting_client", None):        ("Awaiting Client",   "forwarded",      ""),
    ("uat", None):                    ("In Client UAT",     "uat",            ""),
    ("resolved", None):               ("Resolved",          "resolved",       ""),
    ("closed", None):                 ("Closed",            "closed",         ""),
    ("rejected", None):               ("Rejected",          "rejected",       ""),
    ("cancelled", None):              ("Cancelled",         "rejected",       ""),
}


@register.simple_tag
def dev_ticket_badge(ticket):
    """Render the developer-facing status/stage badge for a ticket."""
    sub = ticket.sub_status if ticket.status == "in_progress" else None
    label, css, title = DEV_TICKET_BADGES.get(
        (ticket.status, sub), (ticket.get_status_display(), ticket.status, "")
    )
    if title:
        return format_html(
            '<span class="tw-status-badge tw-status-badge--{}" title="{}">{}</span>',
            css, title, label,
        )
    return format_html(
        '<span class="tw-status-badge tw-status-badge--{}">{}</span>', css, label
    )


# ── Timeline event helpers — data lives in shared_ticket_extras ──────────────

register.filter("event_label", _event_label)
register.filter("event_dot_cls", _event_dot_cls)
register.filter("event_icon", _event_icon)
