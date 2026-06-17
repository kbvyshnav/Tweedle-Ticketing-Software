"""Shared timeline event data and helpers.

Plain Python module — not a Django templatetag library. Imported by
portal-specific tag libraries (client_extras, dev_extras) which register
the three filter functions under their own `register` instances.
"""

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


def event_label(action):
    return EVENT_LABELS.get(action, action.replace("_", " ").title())


def event_dot_cls(action):
    return EVENT_DOT_CLS.get(action, "work")


def event_icon(action):
    return EVENT_ICONS.get(action, "bx-time-five")
