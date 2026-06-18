"""Client-portal display helpers.

The role-aware status badge now lives in the shared matrix
(``tickets.labels`` + ``{% load ticket_labels %}``); the old
``CLIENT_TICKET_BADGES`` dict and ``client_ticket_badge`` tag were removed when
the client portal migrated onto it. This module now only re-exports the timeline
event helpers that the client detail template still uses.
"""

from django import template

from tickets.templatetags.shared_ticket_extras import (
    event_dot_cls as _event_dot_cls,
    event_icon as _event_icon,
    event_label as _event_label,
)

register = template.Library()


# ── Timeline event helpers — data lives in shared_ticket_extras ──────────────

register.filter("event_label", _event_label)
register.filter("event_dot_cls", _event_dot_cls)
register.filter("event_icon", _event_icon)
