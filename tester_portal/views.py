from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.auth import RoleRequiredMixin, role_required
from tickets.chat import ChatError, post_ticket_message
from tickets.models import Ticket
from tickets.transitions import InvalidTransition, TransitionNotAllowed, TransitionValidationError, transition

S = Ticket.Status
SS = Ticket.SubStatus

ALLOWED_ACTIONS = {"pass", "fail"}

VISIBLE_SUB_STATUSES = [SS.TESTING, SS.RETURNED, SS.READY_FOR_UAT]


class TesterDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = {"tester"}
    template_name = "tester_portal/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            Ticket.objects.filter(
                assigned_tester=self.request.user,
                status=S.IN_PROGRESS,
                sub_status__in=VISIBLE_SUB_STATUSES,
            )
            .select_related("client", "assigned_developer", "assigned_tester")
            .order_by("-created_at")
        )
        ctx["assigned_tickets"] = qs
        ctx["testing_count"] = qs.filter(sub_status=SS.TESTING).count()
        ctx["passed_count"] = qs.filter(sub_status=SS.READY_FOR_UAT).count()
        ctx["failed_count"] = qs.filter(sub_status=SS.RETURNED).count()
        ctx["active_nav"] = "dashboard"
        return ctx


@role_required("tester")
def tester_ticket_detail(request, pk):
    ticket = get_object_or_404(
        Ticket,
        pk=pk,
        assigned_tester=request.user,
        status=S.IN_PROGRESS,
        sub_status__in=VISIBLE_SUB_STATUSES,
    )
    return render(request, "tester_portal/ticket-detail.html", {
        "ticket": ticket,
        "events": ticket.events.select_related("actor").order_by("created_at", "id"),
        "chat_messages": ticket.messages.select_related("author").order_by("created_at", "id"),
        "active_nav": "dashboard",
    })


@role_required("tester")
@require_POST
def tester_ticket_transition(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, assigned_tester=request.user)
    action = request.POST.get("action", "")

    if action not in ALLOWED_ACTIONS:
        messages.error(request, "Invalid action.")
        return redirect("tester:ticket_detail", pk=pk)

    data = {}
    if action == "fail":
        data["failure_notes"] = request.POST.get("failure_notes", "").strip()

    try:
        transition(ticket, action, actor=request.user, **data)
        messages.success(request, "Ticket updated successfully.")
    except (InvalidTransition, TransitionNotAllowed, TransitionValidationError) as exc:
        messages.error(request, str(exc))

    return redirect("tester:ticket_detail", pk=pk)


@role_required("tester")
@require_POST
def tester_post_message(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, assigned_tester=request.user)
    try:
        post_ticket_message(ticket, request.user, request.POST.get("body", ""))
        messages.success(request, "Message sent.")
    except ChatError as exc:
        messages.error(request, str(exc))
    return redirect("tester:ticket_detail", pk=pk)
