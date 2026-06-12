"""Admin-portal display helpers.

The admin-facing (status, sub_status) -> badge mapping lives here as a plain
data dict so it can be lifted cleanly into a shared, role-aware module later
(TARGET §6 defines a different label slice per portal). Keep this dict pure
data — no logic woven in — so centralizing stays trivial.
"""

from django import template
from django.utils.html import format_html

register = template.Library()

# key: (status, sub_status_or_None) -> (admin label, CSS modifier, title|"")
# Admin column of TARGET_TICKET_FLOW.md §6. CSS modifiers reuse the existing
# tw-status-badge--* classes already styled in dashboard.css.
ADMIN_TICKET_BADGES = {
    ("new", None): ("New", "new", ""),
    ("in_progress", "development"): ("Development", "development", ""),
    ("in_progress", "testing"): ("Testing", "testing", ""),
    ("in_progress", "returned"): ("Returned", "returned", "Returned from Testing"),
    ("in_progress", "ready_for_uat"): (
        "Ready for UAT", "testing-passed", "Testing Passed — Ready for UAT"),
    ("awaiting_client", None): ("Awaiting Client", "forwarded", ""),
    ("uat", None): ("UAT Approval", "uat", ""),
    ("resolved", None): ("Resolved", "resolved", ""),
    ("closed", None): ("Closed", "closed", ""),
    ("rejected", None): ("Rejected", "rejected", ""),
    ("cancelled", None): ("Cancelled", "rejected", ""),
}


@register.simple_tag
def ticket_badge(ticket):
    """Render the admin status/stage badge for a ticket."""
    sub = ticket.sub_status if ticket.status == "in_progress" else None
    label, css, title = ADMIN_TICKET_BADGES.get(
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
