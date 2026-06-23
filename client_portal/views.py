from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.utils import timezone

from core.auth import RoleRequiredMixin, role_required
from tickets.chat import ChatError, post_ticket_message
from tickets.models import Ticket
from tickets.transitions import (
    REOPEN_WINDOW_DAYS,
    InvalidTransition,
    TransitionNotAllowed,
    TransitionValidationError,
    transition,
)

from .forms import TicketSubmitForm

S = Ticket.Status

ALLOWED_ACTIONS = {"approve", "request_changes", "cancel", "reopen"}


class ClientDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = {"client"}
    template_name = "client_portal/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            Ticket.objects.filter(client=self.request.user.client)
            .select_related("requester", "assigned_developer", "assigned_tester")
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
        ctx["closed_count"] = qs.filter(status=S.CLOSED).count()
        ctx["rejected_count"] = qs.filter(status=S.REJECTED).count()
        ctx["active_nav"] = "dashboard"
        return ctx


@role_required("client")
def client_ticket_detail(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            "requester", "client", "assigned_developer", "assigned_tester", "accepted_by"
        ),
        pk=pk,
        client=request.user.client,
    )

    reopen_available = False
    if ticket.status == S.CLOSED and ticket.closed_at:
        reopen_available = (
            timezone.now() - ticket.closed_at <= timedelta(days=REOPEN_WINDOW_DAYS)
        )

    reject_event = None
    if ticket.status == S.REJECTED:
        reject_event = ticket.events.filter(action="reject").first()

    return render(
        request,
        "client_portal/ticket-detail.html",
        {
            "ticket": ticket,
            "events": ticket.events.select_related("actor").order_by("created_at", "id"),
            "chat_messages": ticket.messages.select_related("author").order_by(
                "created_at", "id"
            ),
            "reopen_available": reopen_available,
            "reject_event": reject_event,
            "active_nav": "dashboard",
        },
    )


@role_required("client")
def client_submit_ticket(request):
    if request.method == "POST":
        form = TicketSubmitForm(request.POST)
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
            return redirect("client_dashboard")
    else:
        form = TicketSubmitForm()

    return render(
        request,
        "client_portal/submit-ticket.html",
        {"form": form, "active_nav": "submit"},
    )


@require_POST
@role_required("client")
def client_ticket_transition(request, pk):
    ticket = get_object_or_404(
        Ticket,
        pk=pk,
        client=request.user.client,
    )
    action = request.POST.get("action", "")

    if action not in ALLOWED_ACTIONS:
        messages.error(request, f"Unsupported action: '{action}'.")
        return redirect("client_dashboard")

    data = {}
    if action == "request_changes":
        data["feedback"] = request.POST.get("feedback", "").strip()
    elif action == "reopen":
        data["reason"] = request.POST.get("reason", "").strip()

    try:
        transition(ticket, action, actor=request.user, **data)
    except (TransitionNotAllowed, InvalidTransition, TransitionValidationError) as exc:
        messages.error(request, f"Couldn't update {ticket.reference}: {exc}")
    else:
        messages.success(request, _success_msg(action, ticket))

    return redirect("client_dashboard")


@require_POST
@role_required("client")
def client_post_message(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, client=request.user.client)
    try:
        post_ticket_message(ticket, request.user, request.POST.get("body", ""))
        messages.success(request, "Message sent.")
    except ChatError as exc:
        messages.error(request, str(exc))
    return redirect("client_ticket_detail", pk=pk)


def _success_msg(action, ticket):
    ref = ticket.reference
    if action == "approve":
        return f"Ticket {ref} approved — marked as Resolved."
    if action == "request_changes":
        return f"Changes requested on {ref} — ticket returned to development."
    if action == "cancel":
        return f"Ticket {ref} cancelled."
    if action == "reopen":
        return f"Ticket {ref} reopened — work will resume."
    return f"Ticket {ref} updated."
