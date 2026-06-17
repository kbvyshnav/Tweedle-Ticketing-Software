"""Sub-user portal display helpers (TARGET §6 sub-user column)."""

from django import template
from django.utils.html import format_html

from tickets.templatetags.shared_ticket_extras import (
    event_dot_cls as _event_dot_cls,
    event_icon as _event_icon,
    event_label as _event_label,
)

register = template.Library()

SUBUSER_TICKET_BADGES = {
    ("new", None):                    ("New — Received",       "new",      ""),
    ("in_progress", "development"):   ("In Progress",          "progress", ""),
    ("in_progress", "testing"):       ("In Progress",          "progress", ""),
    ("in_progress", "returned"):      ("In Progress",          "progress", ""),
    ("in_progress", "ready_for_uat"): ("In Progress",          "progress", ""),
    ("awaiting_client", None):        ("Your Input Needed",    "forwarded","Awaiting your response"),
    ("uat", None):                    ("Please Verify",        "uat",      "Awaiting your verification"),
    ("resolved", None):               ("Awaiting Closure",     "resolved", ""),
    ("closed", None):                 ("Completed",            "closed",   ""),
    ("rejected", None):               ("Not Accepted",         "rejected", ""),
    ("cancelled", None):              ("Cancelled",            "rejected", ""),
}


@register.simple_tag
def subuser_ticket_badge(ticket):
    # Two-state UAT: confirmed sub-users see a different label
    if ticket.status == "uat" and ticket.subuser_confirmed:
        return format_html(
            '<span class="tw-status-badge tw-status-badge--uat"'
            ' title="Sub-user confirmed — awaiting client approval">'
            'Confirmed — Awaiting Approval</span>'
        )
    sub = ticket.sub_status if ticket.status == "in_progress" else None
    label, css, title = SUBUSER_TICKET_BADGES.get(
        (ticket.status, sub),
        (ticket.get_status_display(), ticket.status, ""),
    )
    if title:
        return format_html(
            '<span class="tw-status-badge tw-status-badge--{}" title="{}">{}</span>',
            css, title, label,
        )
    return format_html(
        '<span class="tw-status-badge tw-status-badge--{}">{}</span>',
        css, label,
    )


register.filter("event_label", _event_label)
register.filter("event_dot_cls", _event_dot_cls)
register.filter("event_icon", _event_icon)
