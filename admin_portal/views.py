from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
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
SS = Ticket.SubStatus

# Dashboard tab key -> the ticket status it lists.
TAB_STATUS = {
    "inbox": S.NEW,
    "inprogress": S.IN_PROGRESS,
    "forwarded": S.AWAITING_CLIENT,
    "uat": S.UAT,
    "resolved": S.RESOLVED,
    "closed": S.CLOSED,
    "rejected": S.REJECTED,
    "cancelled": S.CANCELLED,
}

# Actions this admin endpoint exposes: list-level (Phase 4.2) plus the
# details-modal actions (Phase 4.3). The engine still re-checks each one.
ALLOWED_ACTIONS = {
    "assign", "reject", "resume", "send_to_uat",      # 4.2 list-level
    "request_info", "reassign", "request_changes", "close",  # 4.3 modal
    "reopen", "restore",  # reopen: resolved/closed -> in_progress; restore: rejected -> new
    "cancel",  # cancel: new/in_progress/awaiting_client -> cancelled (reason optional)
}


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
    if action in ("assign", "reassign"):
        # assign requires a developer; reassign needs developer and/or tester
        # (the engine guard enforces "at least one" for reassign).
        dev_pk = request.POST.get("developer")
        if dev_pk:
            data["developer"] = get_object_or_404(User, pk=dev_pk, role="developer")
        tester_pk = request.POST.get("tester")
        if tester_pk:
            data["tester"] = get_object_or_404(User, pk=tester_pk, role="tester")
    elif action in ("reject", "reopen", "cancel"):
        # cancel's reason is optional (T3) — an empty string is fine.
        data["reason"] = request.POST.get("reason", "").strip()
    elif action == "request_info":
        data["message"] = request.POST.get("message", "").strip()
    elif action == "request_changes":
        data["feedback"] = request.POST.get("feedback", "").strip()

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
    if action == "reassign":
        who = []
        if data.get("developer"):
            who.append(f"developer {data['developer'].username}")
        if data.get("tester"):
            who.append(f"tester {data['tester'].username}")
        return f"Ticket {ref} reassigned ({', '.join(who)})."
    if action == "reject":
        return f"Ticket {ref} rejected."
    if action == "resume":
        return f"Ticket {ref} resumed — back in progress."
    if action == "send_to_uat":
        return f"Ticket {ref} sent to client for UAT."
    if action == "request_info":
        return f"Ticket {ref} — information requested from the client."
    if action == "request_changes":
        return f"Ticket {ref} recalled to development."
    if action == "close":
        return f"Ticket {ref} closed."
    if action == "reopen":
        return f"Ticket {ref} reopened — back in development."
    if action == "restore":
        return f"Ticket {ref} restored to the inbox as New."
    if action == "cancel":
        return f"Ticket {ref} cancelled."
    return f"Ticket {ref} updated."


@role_required("admin")
def admin_ticket_detail(request, pk):
    """Server-rendered detail partial for the admin ticket-details modal.

    Read-only details + timeline (TicketEvents) + chat (TicketMessages), plus
    the action forms whose visibility matches what the engine allows for the
    ticket's current status. Admin-only; fetched and injected by the dashboard.
    """
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            "requester", "client", "assigned_developer", "assigned_tester", "accepted_by"
        ),
        pk=pk,
    )
    # Workload counts surfaced on the Assign/Reassign <option>s (Issue 1b).
    # All dev annotations target the same `dev_tickets` reverse relation (and all
    # tester annotations the same `test_tickets`), so Django uses one join + a
    # FILTER/CASE per count — they don't inflate each other.
    developers = (
        User.objects.filter(role="developer")
        .annotate(
            wl_active=Count(
                "dev_tickets",
                filter=Q(dev_tickets__status__in=[S.IN_PROGRESS, S.AWAITING_CLIENT]),
            ),
            wl_in_dev=Count(
                "dev_tickets",
                filter=Q(
                    dev_tickets__status=S.IN_PROGRESS,
                    dev_tickets__sub_status__in=[SS.DEVELOPMENT, SS.RETURNED],
                ),
            ),
            wl_in_uat=Count("dev_tickets", filter=Q(dev_tickets__status=S.UAT)),
        )
        .order_by("username")
    )
    testers = (
        User.objects.filter(role="tester")
        .annotate(
            wl_in_testing=Count(
                "test_tickets",
                filter=Q(
                    test_tickets__status=S.IN_PROGRESS,
                    test_tickets__sub_status=SS.TESTING,
                ),
            ),
            wl_queued=Count(
                "test_tickets",
                filter=Q(
                    test_tickets__status=S.IN_PROGRESS,
                    test_tickets__sub_status__in=[SS.RETURNED, SS.READY_FOR_UAT],
                ),
            ),
            wl_active=Count(
                "test_tickets",
                filter=Q(
                    test_tickets__status=S.IN_PROGRESS,
                    test_tickets__sub_status__in=[
                        SS.TESTING, SS.RETURNED, SS.READY_FOR_UAT,
                    ],
                ),
            ),
        )
        .order_by("username")
    )
    context = {
        "ticket": ticket,
        "developers": developers,
        "testers": testers,
    }
    return render(request, "admin_portal/_ticket_detail.html", context)


@role_required("admin")
def admin_ticket_timeline(request, pk):
    """Admin-only timeline drawer: the ticket's real TicketEvents (ordered)."""
    ticket = get_object_or_404(Ticket, pk=pk)
    return render(
        request,
        "admin_portal/_ticket_timeline.html",
        {"ticket": ticket, "events": ticket.events.select_related("actor").all()},
    )


@role_required("admin")
def admin_ticket_chat(request, pk):
    """Admin-only chat drawer: the ticket's real TicketMessages (read-only)."""
    ticket = get_object_or_404(Ticket, pk=pk)
    return render(
        request,
        "admin_portal/_ticket_chat.html",
        {"ticket": ticket, "chat_messages": ticket.messages.select_related("author").all()},
    )
