from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.auth import RoleRequiredMixin, role_required
from tickets.chat import ChatError, post_ticket_message
from tickets.models import Ticket
from tickets.transitions import (
    InvalidTransition,
    TransitionNotAllowed,
    TransitionValidationError,
    transition,
)

from .forms import SubuserTicketSubmitForm

S = Ticket.Status

ALLOWED_ACTIONS = {"confirm", "request_changes"}


class SubuserDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = {"subuser"}
    template_name = "subuser_portal/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            Ticket.objects.filter(requester=self.request.user)
            .select_related("requester", "client", "assigned_developer", "assigned_tester")
            .order_by("-created_at")
        )
        ctx["tickets"] = qs
        ctx["open_count"] = qs.filter(
            status__in=[S.NEW, S.IN_PROGRESS, S.AWAITING_CLIENT, S.UAT]
        ).count()
        ctx["needs_action_count"] = qs.filter(
            status__in=[S.AWAITING_CLIENT, S.UAT]
        ).count()
        ctx["resolved_count"] = qs.filter(status=S.RESOLVED).count()
        ctx["closed_count"]   = qs.filter(status=S.CLOSED).count()
        ctx["rejected_count"] = qs.filter(status=S.REJECTED).count()
        ctx["active_nav"] = "dashboard"
        return ctx


@role_required("subuser")
def subuser_submit_ticket(request):
    if request.method == "POST":
        form = SubuserTicketSubmitForm(request.POST)
        if form.is_valid():
            Ticket.objects.create(
                subject=form.cleaned_data["subject"],
                description=form.cleaned_data["description"],
                category=form.cleaned_data["category"],
                priority=form.cleaned_data["priority"],
                requester=request.user,
                client=request.user.client,
                status=S.NEW,
            )
            messages.success(request, "Ticket submitted successfully.")
            return redirect("subuser:dashboard")
    else:
        form = SubuserTicketSubmitForm()

    return render(
        request,
        "subuser_portal/submit-ticket.html",
        {"form": form, "active_nav": "submit"},
    )


@role_required("subuser")
def subuser_ticket_detail(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            "requester", "client", "assigned_developer", "assigned_tester"
        ),
        pk=pk,
        requester=request.user,
    )
    return render(
        request,
        "subuser_portal/ticket-detail.html",
        {
            "ticket": ticket,
            "events": ticket.events.select_related("actor").order_by("created_at", "id"),
            "chat_messages": ticket.messages.select_related("author").order_by(
                "created_at", "id"
            ),
            "active_nav": "dashboard",
        },
    )


@require_POST
@role_required("subuser")
def subuser_ticket_transition(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, client=request.user.client)
    action = request.POST.get("action", "")

    if action not in ALLOWED_ACTIONS:
        messages.error(request, f"Unsupported action: '{action}'.")
        return redirect("subuser:dashboard")

    data = {}
    if action == "request_changes":
        data["feedback"] = request.POST.get("feedback", "").strip()

    try:
        transition(ticket, action, actor=request.user, **data)
        messages.success(request, _success_msg(action, ticket))
    except (TransitionNotAllowed, InvalidTransition, TransitionValidationError) as exc:
        messages.error(request, str(exc))

    return redirect("subuser:ticket_detail", pk=pk)


@require_POST
@role_required("subuser")
def subuser_post_message(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, requester=request.user)
    try:
        post_ticket_message(ticket, request.user, request.POST.get("body", ""))
        messages.success(request, "Message sent.")
    except ChatError as exc:
        messages.error(request, str(exc))
    return redirect("subuser:ticket_detail", pk=pk)


def _success_msg(action, ticket):
    ref = ticket.reference
    if action == "confirm":
        return f"Ticket {ref} confirmed — the client has been notified."
    if action == "request_changes":
        return f"Feedback submitted on {ref} — ticket returned to development."
    return f"Ticket {ref} updated."
