from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.auth import RoleRequiredMixin, role_required
from tickets.models import Ticket
from tickets.transitions import (
    InvalidTransition,
    TransitionNotAllowed,
    TransitionValidationError,
    transition,
)

User = get_user_model()
S = Ticket.Status

# Dashboard tab key -> the ticket status it lists.
TAB_STATUS = {
    "inbox": S.NEW,
    "inprogress": S.IN_PROGRESS,
    "forwarded": S.AWAITING_CLIENT,
    "uat": S.UAT,
    "resolved": S.RESOLVED,
    "closed": S.CLOSED,
    "rejected": S.REJECTED,
}

# List-level actions this admin endpoint exposes (Phase 4.2). The details-modal
# actions (request_info/reassign/recall/close) arrive in 4.3.
ALLOWED_ACTIONS = {"assign", "reject", "resume", "send_to_uat"}


class AdminDashboardView(RoleRequiredMixin, TemplateView):
    """Admin portal dashboard.

    Phase 4.1b: read-only data binding — each tab renders its real tickets.
    Phase 4.2: list-level action forms post to `ticket_transition`.
    (cancelled tickets have no tab in this 7-tab design — admin-only for now.)
    """

    allowed_roles = {"admin"}
    template_name = "admin_portal/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = Ticket.objects.select_related(
            "requester", "client", "assigned_developer", "assigned_tester"
        ).order_by("-created_at")
        for tab, status in TAB_STATUS.items():
            qs = base.filter(status=status)
            ctx[f"{tab}_tickets"] = qs
            ctx[f"{tab}_count"] = qs.count()
        # Assignment-modal selects come from real users.
        ctx["developers"] = User.objects.filter(role="developer").order_by("username")
        ctx["testers"] = User.objects.filter(role="tester").order_by("username")
        return ctx


@require_POST
@role_required("admin")
def ticket_transition(request, pk):
    """Generic admin action endpoint: POST action -> transition() -> redirect.

    Admin-only for this phase. transition() re-checks role/legal/guard, so the
    engine remains the real authority. Engine errors surface as messages (never
    a 500); always redirects back to the dashboard.
    """
    ticket = get_object_or_404(Ticket, pk=pk)
    action = request.POST.get("action", "")

    if action not in ALLOWED_ACTIONS:
        messages.error(request, f"Unsupported action: '{action}'.")
        return redirect("admin_dashboard")

    data = {}
    if action == "assign":
        dev_pk = request.POST.get("developer")
        if dev_pk:
            data["developer"] = get_object_or_404(User, pk=dev_pk, role="developer")
        tester_pk = request.POST.get("tester")
        if tester_pk:
            data["tester"] = get_object_or_404(User, pk=tester_pk, role="tester")
    elif action == "reject":
        data["reason"] = request.POST.get("reason", "").strip()

    try:
        transition(ticket, action, actor=request.user, **data)
    except (TransitionNotAllowed, InvalidTransition, TransitionValidationError) as exc:
        messages.error(request, f"Couldn't update ticket {ticket.reference}: {exc}")
    else:
        messages.success(request, _success_message(action, ticket, data))
    return redirect("admin_dashboard")


def _success_message(action, ticket, data):
    ref = ticket.reference
    if action == "assign":
        dev = data["developer"].username
        tester = data.get("tester")
        if tester:
            return f"Ticket {ref} assigned to {dev} (tester {tester.username})."
        return f"Ticket {ref} assigned to {dev}."
    if action == "reject":
        return f"Ticket {ref} rejected."
    if action == "resume":
        return f"Ticket {ref} resumed — back in progress."
    if action == "send_to_uat":
        return f"Ticket {ref} sent to client for UAT."
    return f"Ticket {ref} updated."
