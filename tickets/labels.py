"""Shared, role-aware ticket-label matrix — the single source of truth for
turning a (role, status, sub_status, subuser_confirmed) tuple into a display
(label, css-modifier, title), transcribed VERBATIM from TARGET_TICKET_FLOW.md §6.

Pure data + a pure resolver: no Django template machinery here, so the matrix
stays trivially unit-testable. The registered template tags that render this
data live in ``tickets/templatetags/ticket_labels.py`` and call into here.

Status / sub-status strings come from TARGET §3 only (``Ticket.Status`` /
``Ticket.SubStatus``); never the legacy ``forwarded`` / ``testing_passed`` /
``uat_prep`` strings.

Contract: every value is a ``(label, css-modifier, title)`` 3-tuple — the same
shape the legacy per-portal dicts returned, so migrating a portal is a drop-in.
css-modifiers are kept identical to each portal's pre-existing badge map so a
later migration is byte-for-byte equivalent (no colour shift).

NOTE (tracked cosmetic cleanup, intentionally unchanged this step): the
``forwarded`` css modifier still backs ``awaiting_client``, and ``cancelled``
reuses the ``rejected`` style.
"""

# Sentinel sub-key for the `uat + subuser_confirmed` variant. TARGET §6 gives
# admin / client / developer / sub-user a distinct confirmed row; tester is N/A
# across all of uat, so there is no tester confirmed entry.
CONFIRMED = "__subuser_confirmed__"

# key: (role, status, sub_status | None | CONFIRMED) -> (label, css-modifier, title)
# Sub-status is only meaningful while status == "in_progress" (collapsed to None
# otherwise by resolve_ticket_label). Cells that are "N/A" for a role in §6 are
# intentionally ABSENT — the resolver falls back for them.
TICKET_LABELS = {
    # ── admin (TARGET §6 admin column) ───────────────────────────────────
    ("admin", "new", None):                        ("New",               "new",            ""),
    ("admin", "in_progress", "development"):       ("Development",       "development",    ""),
    ("admin", "in_progress", "testing"):           ("Testing",           "testing",        ""),
    ("admin", "in_progress", "returned"):          ("Returned from QA",  "returned",       "Returned from Testing"),
    ("admin", "in_progress", "ready_for_uat"):     ("Ready for UAT",     "testing-passed", "Testing Passed — Ready for UAT"),
    ("admin", "awaiting_client", None):            ("Awaiting Client",   "forwarded",      ""),
    ("admin", "uat", None):                        ("UAT Approval",      "uat",            ""),
    ("admin", "uat", CONFIRMED):                   ("UAT — sub-user confirmed, awaiting client approval", "uat", "Sub-user confirmed — awaiting client approval"),
    ("admin", "resolved", None):                   ("Resolved",          "resolved",       ""),
    ("admin", "closed", None):                     ("Closed",            "closed",         ""),
    ("admin", "rejected", None):                   ("Rejected",          "rejected",       ""),
    ("admin", "cancelled", None):                  ("Cancelled",         "rejected",       ""),

    # ── client (TARGET §6 client column) ─────────────────────────────────
    ("client", "new", None):                       ("New — Received",    "new",            ""),
    ("client", "in_progress", "development"):      ("In Progress",       "progress",       ""),
    ("client", "in_progress", "testing"):          ("In Progress",       "progress",       ""),
    ("client", "in_progress", "returned"):         ("In Progress",       "progress",       ""),
    ("client", "in_progress", "ready_for_uat"):    ("In Progress",       "progress",       ""),
    ("client", "awaiting_client", None):           ("Your Input Needed", "forwarded",      ""),
    ("client", "uat", None):                       ("Ready for Your Review", "uat",        ""),
    ("client", "uat", CONFIRMED):                  ("Ready for Your Review (sub-user confirmed)", "uat", "Sub-user confirmed — awaiting your approval"),
    ("client", "resolved", None):                  ("Awaiting Closure",  "resolved",       ""),
    ("client", "closed", None):                    ("Completed",         "closed",         ""),
    ("client", "rejected", None):                  ("Not Accepted",      "rejected",       ""),
    ("client", "cancelled", None):                 ("Cancelled",         "rejected",       ""),

    # ── developer (TARGET §6 developer column) ───────────────────────────
    # new, rejected = N/A for developers (absent).
    ("developer", "in_progress", "development"):   ("Development",       "development",    ""),
    ("developer", "in_progress", "testing"):       ("In Testing",        "testing",        ""),
    ("developer", "in_progress", "returned"):      ("Returned from QA",  "returned",       "Returned from Testing"),
    ("developer", "in_progress", "ready_for_uat"): ("Ready for UAT",     "testing-passed", "Testing Passed — Ready for UAT"),
    ("developer", "awaiting_client", None):        ("Paused — Awaiting Client", "forwarded", ""),
    ("developer", "uat", None):                    ("In Client UAT",     "uat",            ""),
    ("developer", "uat", CONFIRMED):               ("In Client UAT",     "uat",            ""),
    ("developer", "resolved", None):               ("Resolved",          "resolved",       ""),
    ("developer", "closed", None):                 ("Closed",            "closed",         ""),
    ("developer", "cancelled", None):              ("Cancelled",         "rejected",       ""),

    # ── tester (TARGET §6 tester column) ─────────────────────────────────
    # Only the three testing sub-stages are visible; everything else is N/A.
    ("tester", "in_progress", "testing"):          ("Testing",           "testing",        ""),
    ("tester", "in_progress", "returned"):         ("Failed",            "returned",       "Returned to Developer"),
    ("tester", "in_progress", "ready_for_uat"):    ("Passed",            "testing-passed", "Testing Passed — Ready for UAT"),

    # ── sub-user (TARGET §6 sub-user column) ─────────────────────────────
    ("subuser", "new", None):                      ("New — Received",    "new",            ""),
    ("subuser", "in_progress", "development"):     ("In Progress",       "progress",       ""),
    ("subuser", "in_progress", "testing"):         ("In Progress",       "progress",       ""),
    ("subuser", "in_progress", "returned"):        ("In Progress",       "progress",       ""),
    ("subuser", "in_progress", "ready_for_uat"):   ("In Progress",       "progress",       ""),
    ("subuser", "awaiting_client", None):          ("Your Input Needed", "forwarded",      "Awaiting your response"),
    ("subuser", "uat", None):                      ("Please Verify",     "uat",            "Awaiting your verification"),
    ("subuser", "uat", CONFIRMED):                 ("Confirmed — Awaiting Approval", "uat", "Sub-user confirmed — awaiting client approval"),
    ("subuser", "resolved", None):                 ("Awaiting Closure",  "resolved",       ""),
    ("subuser", "closed", None):                   ("Completed",         "closed",         ""),
    ("subuser", "rejected", None):                 ("Not Accepted",      "rejected",       ""),
    ("subuser", "cancelled", None):                ("Cancelled",         "rejected",       ""),
}


def resolve_ticket_label(role, status, sub_status, subuser_confirmed=False, fallback=None):
    """Resolve a ``(label, css-modifier, title)`` for a (role, state) tuple per §6.

    ``sub_status`` is only meaningful while ``status == "in_progress"`` (collapsed
    to ``None`` otherwise, matching the legacy per-portal tags). On a ``uat``
    ticket with ``subuser_confirmed`` truthy the confirmed variant is tried first.

    Unknown keys (e.g. a state that is N/A for the role) return ``fallback`` if
    given, else a derived ``(status, status, "")`` default.
    """
    sub = sub_status if status == "in_progress" else None
    if status == "uat" and subuser_confirmed:
        hit = TICKET_LABELS.get((role, status, CONFIRMED))
        if hit is not None:
            return hit
    hit = TICKET_LABELS.get((role, status, sub))
    if hit is not None:
        return hit
    if fallback is not None:
        return fallback
    return (status, status, "")
