"""Client-portal display helpers (TARGET §6 client column)."""

from django import template
from django.utils.html import format_html

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


# ── Timeline event helpers ────────────────────────────────────────────────────

EVENT_LABELS = {
    "assign": "Assigned to Developer",
    "reassigned": "Reassigned",
    "reject": "Rejected",
    "cancel": "Cancelled",
    "request_info": "Information Requested",
    "resume": "Work Resumed",
    "send_to_uat": "Sent for UAT Review",
    "approve": "Approved by Client",
    "request_changes": "Changes Requested",
    "close": "Closed",
    "reopen": "Reopened",
    "restore": "Restored to New",
    "confirm": "Sub-user Confirmed",
    "submit_for_testing": "Submitted for Testing",
    "pass": "Testing Passed",
    "fail": "Testing Failed",
    "resubmit_for_testing": "Resubmitted for Testing",
    "mark_ready": "Marked Ready for UAT",
}

EVENT_DOT_CLS = {
    "assign": "assigned",
    "reassigned": "assigned",
    "reject": "rejected",
    "cancel": "rejected",
    "request_info": "info",
    "resume": "work",
    "send_to_uat": "uat",
    "approve": "resolved",
    "request_changes": "work",
    "close": "closed",
    "reopen": "work",
    "restore": "work",
    "confirm": "assigned",
    "submit_for_testing": "work",
    "pass": "resolved",
    "fail": "rejected",
    "resubmit_for_testing": "work",
    "mark_ready": "uat",
}

EVENT_ICONS = {
    "assign": "bx-user-check",
    "reassigned": "bx-user",
    "reject": "bx-x-circle",
    "cancel": "bx-x-circle",
    "request_info": "bx-info-circle",
    "resume": "bx-play",
    "send_to_uat": "bx-check-shield",
    "approve": "bx-check-circle",
    "request_changes": "bx-revision",
    "close": "bx-lock",
    "reopen": "bx-refresh",
    "restore": "bx-undo",
    "confirm": "bx-user-check",
    "submit_for_testing": "bx-test-tube",
    "pass": "bx-check",
    "fail": "bx-x",
    "resubmit_for_testing": "bx-refresh",
    "mark_ready": "bx-check-shield",
}


@register.filter
def event_label(action):
    return EVENT_LABELS.get(action, action.replace("_", " ").title())


@register.filter
def event_dot_cls(action):
    return EVENT_DOT_CLS.get(action, "work")


@register.filter
def event_icon(action):
    return EVENT_ICONS.get(action, "bx-time-five")
