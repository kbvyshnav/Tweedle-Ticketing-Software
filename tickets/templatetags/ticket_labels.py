"""Shared, role-aware ticket-label template tags (TARGET §6).

Usable from any portal's templates after ``{% load ticket_labels %}``:

- ``{% role_ticket_badge ticket "client" %}`` renders the status badge ``<span>``
  (label + css-modifier + optional title), identical in shape to the legacy
  per-portal badge tags.
- ``{% role_ticket_label ticket "client" %}`` returns just the resolved §6 label
  string (for prose / sentences); supports ``... as var`` assignment.

Both delegate to ``tickets.labels.resolve_ticket_label`` — the single source of
truth — passing the ticket's model display as the fallback.
"""

from django import template
from django.template.defaultfilters import date as _date
from django.utils.html import format_html

from tickets.labels import resolve_ticket_label
from tickets.models import Ticket
from tickets.templatetags.shared_ticket_extras import (
    event_dot_cls as _event_dot_cls,
    event_icon as _event_icon,
    event_label as _event_label,
)

register = template.Library()

# Timeline event helpers (single source: shared_ticket_extras) — registered here
# so any portal can `{% load ticket_labels %}` and render a TicketEvent.action.
register.filter("event_label", _event_label)
register.filter("event_dot_cls", _event_dot_cls)
register.filter("event_icon", _event_icon)

# Raw status/sub_status code → human label, for the timeline from→to meta line
# (ADMIN_FE_REVIEW S9: stop printing raw `new` / `in_progress/development` codes).
_STATUS_LABELS = dict(Ticket.Status.choices)
_SUB_STATUS_LABELS = dict(Ticket.SubStatus.choices)


@register.filter
def status_label(value):
    """'in_progress' → 'In Progress'. Empty/unknown values pass through cleanly."""
    if not value:
        return ""
    return _STATUS_LABELS.get(value, value.replace("_", " ").title())


@register.filter
def sub_status_label(value):
    """'ready_for_uat' → 'Ready for UAT'. Empty/unknown values pass through cleanly."""
    if not value:
        return ""
    return _SUB_STATUS_LABELS.get(value, value.replace("_", " ").title())

# The ONE date/time format for ticket timestamps everywhere (Issue 3 / S5):
# "20 Jun 2026, 2:00 PM". Delegates to Django's built-in date filter so timezone
# localization, locale handling, and None→"" behaviour stay identical to the
# inline `|date:"…"` usages this replaces — just centralized.
TW_DATETIME_FMT = "d M Y, g:i A"


@register.filter
def tw_datetime(value):
    """Render a ticket timestamp in the single Tweedle standard format."""
    return _date(value, TW_DATETIME_FMT)


def _resolve(ticket, role):
    return resolve_ticket_label(
        role,
        ticket.status,
        ticket.sub_status,
        subuser_confirmed=ticket.subuser_confirmed,
        fallback=(ticket.get_status_display(), ticket.status, ""),
    )


@register.simple_tag
def role_ticket_badge(ticket, role):
    """Render the role-appropriate status badge span for a ticket."""
    label, css, title = _resolve(ticket, role)
    if title:
        return format_html(
            '<span class="tw-status-badge tw-status-badge--{}" title="{}">{}</span>',
            css, title, label,
        )
    return format_html(
        '<span class="tw-status-badge tw-status-badge--{}">{}</span>', css, label
    )


@register.simple_tag
def role_ticket_label(ticket, role):
    """Return just the role-appropriate §6 label string for a ticket."""
    label, _css, _title = _resolve(ticket, role)
    return label


@register.simple_tag
def role_status_data_attrs(ticket, role):
    """Emit ``data-status-label`` + ``data-status-css`` for a row element.

    Lets client-side features (e.g. the admin global-search dropdown) render the
    matrix §6 label + css-modifier without re-deriving status text in JS. Both
    values are matrix-resolved (sub-status- and subuser_confirmed-aware) and
    escaped for the HTML attribute context.
    """
    label, css, _title = _resolve(ticket, role)
    return format_html('data-status-label="{}" data-status-css="{}"', label, css)
