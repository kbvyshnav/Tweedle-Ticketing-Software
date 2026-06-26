from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.utils import timezone

from core.auth import RoleRequiredMixin, role_required
from tickets.attachments import save_attachments
from tickets.chat import ChatError, post_ticket_message
from tickets.models import Ticket, TicketMessage
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
            "requester", "client", "assigned_developer", "assigned_tester",
            "accepted_by", "linked_from",
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

    info_request = None
    if ticket.status == S.AWAITING_CLIENT:
        info_request = (
            ticket.messages.filter(kind=TicketMessage.Kind.INFO_REQUEST)
            .select_related("author")
            .last()
        )

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
            "info_request": info_request,
            "active_nav": "dashboard",
        },
    )


def _related_ticket(request, raw):
    """Resolve a `related` ticket id to one of the client's own tickets, or None.

    Scoping to `client=request.user.client` means a tampered/foreign id simply
    yields None (the new ticket is created unlinked) — no cross-org leak.
    """
    if not raw:
        return None
    return Ticket.objects.filter(pk=raw, client=request.user.client).first()


@role_required("client")
def client_submit_ticket(request):
    if request.method == "POST":
        form = TicketSubmitForm(request.POST, request.FILES)
        related_ticket = _related_ticket(request, request.POST.get("related"))
        if form.is_valid():
            ticket = Ticket.objects.create(
                subject=form.cleaned_data["subject"],
                description=form.cleaned_data["description"],
                category=form.cleaned_data["category"],
                priority=form.cleaned_data["priority"],
                requester=request.user,
                client=request.user.client,
                status=S.NEW,
                linked_from=related_ticket,
            )
            save_attachments(ticket, form.cleaned_data["attachments"], request.user)
            if related_ticket:
                messages.success(
                    request,
                    f"Ticket submitted — linked to {related_ticket.reference}.",
                )
            else:
                messages.success(request, "Ticket submitted successfully.")
            return redirect("client_dashboard")
    else:
        related_ticket = _related_ticket(request, request.GET.get("related"))
        initial = {}
        if related_ticket:
            initial["subject"] = f"Follow-up: {related_ticket.subject}"[:255]
        form = TicketSubmitForm(initial=initial)

    return render(
        request,
        "client_portal/submit-ticket.html",
        {"form": form, "active_nav": "submit", "related_ticket": related_ticket},
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
