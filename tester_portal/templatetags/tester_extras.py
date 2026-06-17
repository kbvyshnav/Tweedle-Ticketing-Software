"""Tester-portal display helpers (TARGET §6 tester column)."""
from django import template
from django.utils.html import format_html

from tickets.templatetags.shared_ticket_extras import (
    event_dot_cls as _event_dot_cls,
    event_icon as _event_icon,
    event_label as _event_label,
)

register = template.Library()

TESTER_TICKET_BADGES = {
    ("in_progress", "testing"):       ("Testing",  "testing",        ""),
    ("in_progress", "returned"):      ("Failed",   "returned",       "Returned to Developer"),
    ("in_progress", "ready_for_uat"): ("Passed",   "testing-passed", "Testing Passed — Ready for UAT"),
}


@register.simple_tag
def tester_ticket_badge(ticket):
    sub = ticket.sub_status if ticket.status == "in_progress" else None
    label, css, title = TESTER_TICKET_BADGES.get(
        (ticket.status, sub), (ticket.get_status_display(), ticket.status, "")
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


# ── Timeline event helpers — data lives in shared_ticket_extras ──────────────
register.filter("event_label", _event_label)
register.filter("event_dot_cls", _event_dot_cls)
register.filter("event_icon", _event_icon)
