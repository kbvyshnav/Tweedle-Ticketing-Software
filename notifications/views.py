"""In-app notification feed + read-state endpoints (Phase 4.20, P1).

Three views, all scoped to ``request.user`` (you only ever see/modify your own
notifications):

- ``notifications_feed``  — the full list page (rendered into each role's base).
- ``notification_open``   — mark one read, then deep-link to its ticket.
- ``mark_all_read``       — mark every unread one read (POST).

Notification *creation* still happens in the transition engine and the chat
helper; this module only renders and flips ``is_read``.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .context_processors import STATUS_TAB
from .models import Notification

# Each role's base template — the feed page extends the caller's own themed base.
BASE_FOR_ROLE = {
    "admin": "base.html",
    "client": "client_base.html",
    "subuser": "subuser_base.html",
    "developer": "developer_base.html",
    "tester": "tester_base.html",
}

# Each role's standalone ticket-detail URL name. Admin has no detail page (the
# ticket opens in a modal on the dashboard), so it is handled separately below.
_ROLE_TICKET_URL = {
    "client": "client_ticket_detail",
    "subuser": "subuser:ticket_detail",
    "developer": "dev:ticket_detail",
    "tester": "tester:ticket_detail",
}


def _ticket_target(user, notification):
    """Where opening this notification should land the user."""
    ticket = notification.ticket
    if ticket is None:
        return reverse("notifications_feed")
    if user.role == "admin":
        # Land on the dashboard; ``?open=<ref>&tab=<tab>`` lets it switch to the
        # right tab and auto-open the ticket modal (handled in dashboard.html).
        tab = STATUS_TAB.get(ticket.status) or ""
        return f"{reverse('admin_dashboard')}?open={ticket.reference}&tab={tab}"
    name = _ROLE_TICKET_URL.get(user.role)
    if not name:
        return reverse("notifications_feed")
    return reverse(name, args=[ticket.pk])


@login_required
def notifications_feed(request):
    items = list(
        Notification.objects.filter(recipient=request.user).select_related(
            "ticket", "actor"
        )
    )
    return render(
        request,
        "notifications/feed.html",
        {
            "notifications": items,
            "unread_total": sum(1 for n in items if not n.is_read),
            "base_template": BASE_FOR_ROLE.get(request.user.role, "base.html"),
            "active_nav": "notifications",
        },
    )


@login_required
def notification_open(request, pk):
    """Mark one notification read, then redirect to its ticket (or the feed)."""
    n = get_object_or_404(
        Notification.objects.select_related("ticket"), pk=pk, recipient=request.user
    )
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    return redirect(_ticket_target(request.user, n))


@require_POST
@login_required
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True
    )
    return redirect(request.POST.get("next") or "notifications_feed")
