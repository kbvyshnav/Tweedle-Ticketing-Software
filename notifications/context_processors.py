"""Template context for the in-app notification bell (sweep S4).

The bell lives in the shared admin ``base.html`` and therefore renders on every
admin page. A context processor (rather than a per-view mixin) is the right home:
one registration in ``TEMPLATES`` exposes the unread count + a bounded recent
list to every page that extends the base, without wiring each view by hand.

Read-only display only: this does NOT mark anything as read.
"""

from admin_portal.views import TAB_STATUS
from .models import Notification

# Reverse of admin_portal's TAB_STATUS: a ticket's status -> the dashboard tab
# key its row lives under. Used so a notification click can fire
# ``tweedle:openTicket`` with the right tab (handled in dashboard.html).
# Degrades gracefully: a status with no tab yields ``None`` -> the click still
# opens the ticket, it just doesn't switch tabs.
STATUS_TAB = {status: tab for tab, status in TAB_STATUS.items()}

# Cap the dropdown list so the bell adds at most one bounded query per page.
RECENT_LIMIT = 10


def notifications(request):
    """Expose ``unread_notification_count`` + ``recent_notifications``.

    Empty for anonymous requests so login/error pages stay cheap.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    recent = list(
        Notification.objects.filter(recipient=user).select_related(
            "ticket", "actor"
        )[:RECENT_LIMIT]
    )
    for n in recent:
        # ``ticket`` is nullable; only attach a tab when there is one.
        n.tab = STATUS_TAB.get(n.ticket.status) if n.ticket else None

    return {
        "unread_notification_count": Notification.objects.filter(
            recipient=user, is_read=False
        ).count(),
        "recent_notifications": recent,
    }
