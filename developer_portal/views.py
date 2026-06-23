from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.utils import timezone

from core.auth import RoleRequiredMixin, role_required
from tickets.chat import ChatError, post_ticket_message
from tickets.models import Ticket
from tickets.transitions import InvalidTransition, TransitionNotAllowed, transition

S = Ticket.Status
SS = Ticket.SubStatus

ALLOWED_ACTIONS = {"submit_for_testing", "resubmit_for_testing", "mark_ready"}


class DeveloperDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = {"developer"}
    template_name = "developer_portal/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            Ticket.objects.filter(assigned_developer=self.request.user)
            .select_related("client", "assigned_developer", "assigned_tester")
            .order_by("-created_at")
        )
        ctx["assigned_tickets"] = qs
        ctx["active_count"] = qs.filter(
            status__in=[S.IN_PROGRESS, S.AWAITING_CLIENT]
        ).count()
        ctx["forwarded_count"] = qs.filter(status=S.AWAITING_CLIENT).count()
        ctx["uat_count"] = qs.filter(status=S.UAT).count()
        ctx["overdue_count"] = 0
        ctx["resolved_closed_count"] = qs.filter(
            status__in=[S.RESOLVED, S.CLOSED]
        ).count()
        ctx["active_nav"] = "dashboard"
        return ctx


@role_required("developer")
def dev_ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, assigned_developer=request.user)

    is_development = ticket.status == S.IN_PROGRESS and ticket.sub_status == SS.DEVELOPMENT
    is_returned = ticket.status == S.IN_PROGRESS and ticket.sub_status == SS.RETURNED
    tester_assigned = bool(ticket.assigned_tester_id)

    return render(request, "developer_portal/ticket-detail.html", {
        "ticket": ticket,
        "events": ticket.events.select_related("actor").order_by("created_at", "id"),
        "chat_messages": ticket.messages.select_related("author").order_by("created_at", "id"),
        "show_submit_for_testing": is_development and tester_assigned,
        "show_mark_ready": is_development and not tester_assigned,
        "show_resubmit": is_returned and tester_assigned,
        "active_nav": "dashboard",
    })


@role_required("developer")
@require_POST
def dev_ticket_transition(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, assigned_developer=request.user)
    action = request.POST.get("action", "")

    if action not in ALLOWED_ACTIONS:
        messages.error(request, "Invalid action.")
        return redirect("dev:ticket_detail", pk=pk)

    try:
        transition(ticket, action, actor=request.user)
        messages.success(request, "Ticket updated successfully.")
    except (InvalidTransition, TransitionNotAllowed) as exc:
        messages.error(request, str(exc))

    return redirect("dev:ticket_detail", pk=pk)


@role_required("developer")
@require_POST
def dev_post_message(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, assigned_developer=request.user)
    try:
        post_ticket_message(ticket, request.user, request.POST.get("body", ""))
        messages.success(request, "Message sent.")
    except ChatError as exc:
        messages.error(request, str(exc))
    return redirect("dev:ticket_detail", pk=pk)
