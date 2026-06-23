from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.models import Client
from core.auth import RoleRequiredMixin, role_required
from tickets.chat import ChatError, post_info_request, post_ticket_message
from tickets.models import Ticket, TicketEvent

from .forms import (
    BrandingSettingsForm,
    ClientOnboardForm,
    OrganisationSettingsForm,
    TeamMemberForm,
)
from .models import NOTIFICATION_EVENTS, OrganisationSettings
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
        ctx["active_nav"] = "dashboard"
        return ctx


# Tickets that count as "active" for a client's active-ticket badge.
OPEN_TICKET_STATUSES = [S.NEW, S.IN_PROGRESS, S.AWAITING_CLIENT, S.UAT]


def _clients_context(form=None):
    """Shared context for the Clients page (list + onboard form)."""
    clients = Client.objects.annotate(
        active_tickets=Count(
            "tickets", filter=Q(tickets__status__in=OPEN_TICKET_STATUSES)
        )
    ).order_by("name")
    return {
        "clients": clients,
        "onboard_form": form if form is not None else ClientOnboardForm(),
        "active_nav": "clients",
    }


@role_required("admin")
def admin_clients(request):
    """Admin Clients page: every client org with its active-ticket count."""
    return render(request, "admin_portal/clients.html", _clients_context())


@require_POST
@role_required("admin")
def admin_onboard_client(request):
    """Create a new client organisation from the onboard modal."""
    form = ClientOnboardForm(request.POST)
    if form.is_valid():
        client = form.save()
        messages.success(request, f"Client {client.name} onboarded successfully.")
        return redirect("admin_clients")

    # Re-render the list with the bound form so the modal reopens with errors.
    messages.error(request, "Please correct the highlighted fields and try again.")
    ctx = _clients_context(form)
    ctx["open_onboard_modal"] = True
    return render(request, "admin_portal/clients.html", ctx)


# ── Team (developers / testers) ──────────────────────────────────────────────

def _team_context(form=None):
    """Shared context for the Team page (member list + add-member form)."""
    members = (
        User.objects.filter(role__in=[User.Role.DEVELOPER, User.Role.TESTER])
        .annotate(
            wl_dev=Count(
                "dev_tickets",
                filter=Q(dev_tickets__status__in=OPEN_TICKET_STATUSES),
                distinct=True,
            ),
            wl_test=Count(
                "test_tickets",
                filter=Q(test_tickets__status__in=OPEN_TICKET_STATUSES),
                distinct=True,
            ),
        )
        .order_by("role", "username")
    )
    return {
        "team_members": members,
        "member_form": form if form is not None else TeamMemberForm(),
        "active_nav": "team",
    }


@role_required("admin")
def admin_team(request):
    """Admin Team page: every developer/tester with their active workload."""
    return render(request, "admin_portal/team.html", _team_context())


@require_POST
@role_required("admin")
def admin_add_team_member(request):
    """Create a new developer/tester login account from the add-member modal."""
    form = TeamMemberForm(request.POST)
    if form.is_valid():
        member = form.save()
        name = member.get_full_name() or member.username
        messages.success(
            request, f"{name} added as {member.get_role_display()} (username: {member.username})."
        )
        return redirect("admin_team")

    messages.error(request, "Please correct the highlighted fields and try again.")
    ctx = _team_context(form)
    ctx["open_member_modal"] = True
    return render(request, "admin_portal/team.html", ctx)


@require_POST
@role_required("admin")
def admin_toggle_team_member(request, pk):
    """Enable/disable a team member's login (flips is_active)."""
    member = get_object_or_404(
        User, pk=pk, role__in=[User.Role.DEVELOPER, User.Role.TESTER]
    )
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])
    name = member.get_full_name() or member.username
    messages.success(
        request, f"{name} {'enabled' if member.is_active else 'disabled'}."
    )
    return redirect("admin_team")


# ── Reports ──────────────────────────────────────────────────────────────────

# Turnaround targets (days) by priority. No SLA model exists yet (P3), so this
# is a documented reporting convention used to flag a ticket's TAT met/missed.
TAT_TARGET_DAYS = {"high": 3, "medium": 5, "low": 7}

# Ticket status -> the compact report status-tag colour class.
STATUS_TAG_CSS = {
    S.NEW: "tw-status-inbox",
    S.IN_PROGRESS: "tw-status-progress",
    S.AWAITING_CLIENT: "tw-status-forwarded",
    S.UAT: "tw-status-uat",
    S.RESOLVED: "tw-status-closed",
    S.CLOSED: "tw-status-closed",
    S.REJECTED: "tw-status-closed",
    S.CANCELLED: "tw-status-closed",
}


@role_required("admin")
def admin_reports(request):
    """Ticket activity report: GET-filterable list + TAT/throughput summary."""
    # Resolution timestamp = the first event that moved the ticket to
    # resolved/closed (turnaround end). Falls back to closed_at for any legacy
    # ticket closed before the event trail existed.
    resolved_event = (
        TicketEvent.objects.filter(
            ticket=OuterRef("pk"), to_status__in=[S.RESOLVED, S.CLOSED]
        )
        .order_by("created_at")
        .values("created_at")[:1]
    )
    tickets = (
        Ticket.objects.select_related("client", "assigned_developer")
        .annotate(resolved_event_at=Subquery(resolved_event))
        .order_by("-created_at")
    )

    f_from = (request.GET.get("from") or "").strip()
    f_to = (request.GET.get("to") or "").strip()
    f_status = request.GET.get("status") or "all"
    f_dev = request.GET.get("developer") or "all"
    f_client = request.GET.get("client") or "all"

    if f_from:
        tickets = tickets.filter(created_at__date__gte=f_from)
    if f_to:
        tickets = tickets.filter(created_at__date__lte=f_to)
    if f_status != "all":
        tickets = tickets.filter(status=f_status)
    if f_dev != "all":
        tickets = tickets.filter(assigned_developer_id=f_dev)
    if f_client != "all":
        tickets = tickets.filter(client_id=f_client)

    rows = []
    tat_met = tat_missed = pending = 0
    for t in tickets:
        target = TAT_TARGET_DAYS.get(t.priority, 5)
        resolved_at = t.resolved_event_at or t.closed_at
        if resolved_at:
            days = (resolved_at - t.created_at).days
            met = days <= target
            tat_met += 1 if met else 0
            tat_missed += 0 if met else 1
            tat = {"text": f"{days} / {target}", "css": "met" if met else "missed"}
        else:
            pending += 1
            tat = None
        rows.append({
            "ticket": t,
            "resolved_at": resolved_at,
            "tat": tat,
            "status_css": STATUS_TAG_CSS.get(t.status, "tw-status-closed"),
        })

    ctx = {
        "active_nav": "reports",
        "rows": rows,
        "total": len(rows),
        "tat_met": tat_met,
        "tat_missed": tat_missed,
        "pending": pending,
        "developers": User.objects.filter(role="developer").order_by("username"),
        "clients": Client.objects.order_by("name"),
        "status_choices": Ticket.Status.choices,
        "filters": {
            "from": f_from, "to": f_to, "status": f_status,
            "developer": f_dev, "client": f_client,
        },
    }
    return render(request, "admin_portal/reports.html", ctx)


# ── Settings ─────────────────────────────────────────────────────────────────

def _settings_context(settings_obj, org_form=None, branding_form=None):
    """Shared context for the Settings page (all three section forms)."""
    return {
        "active_nav": "settings",
        "settings": settings_obj,
        "org_form": org_form or OrganisationSettingsForm(instance=settings_obj),
        "branding_form": branding_form or BrandingSettingsForm(instance=settings_obj),
        "notification_rows": settings_obj.notification_rows(),
    }


@role_required("admin")
def admin_settings(request):
    """Admin Settings page: organisation, email-notification and branding prefs.

    One singleton `OrganisationSettings` row backs all three sections. Each
    section is its own POST (hidden `section` field) so saving one never
    overwrites the others; the page always redirects back to itself with a
    toast (PRG), or re-renders with a bound form when validation fails.
    """
    settings_obj = OrganisationSettings.load()

    if request.method == "POST":
        section = request.POST.get("section")

        if section == "org":
            form = OrganisationSettingsForm(request.POST, instance=settings_obj)
            if form.is_valid():
                form.save()
                messages.success(request, "Organisation settings saved.")
                return redirect("admin_settings")
            messages.error(request, "Please correct the highlighted fields and try again.")
            return render(
                request, "admin_portal/settings.html",
                _settings_context(settings_obj, org_form=form),
            )

        if section == "notifications":
            prefs = {}
            for key, _label in NOTIFICATION_EVENTS:
                prefs[f"{key}_admin"] = bool(request.POST.get(f"{key}_admin"))
                prefs[f"{key}_assignee"] = bool(request.POST.get(f"{key}_assignee"))
            settings_obj.notification_prefs = prefs
            settings_obj.save(update_fields=["notification_prefs", "updated_at"])
            messages.success(request, "Notification settings saved.")
            return redirect("admin_settings")

        if section == "branding":
            form = BrandingSettingsForm(request.POST, request.FILES, instance=settings_obj)
            if form.is_valid():
                form.save()
                messages.success(request, "Branding settings saved.")
                return redirect("admin_settings")
            messages.error(request, "Please correct the highlighted fields and try again.")
            return render(
                request, "admin_portal/settings.html",
                _settings_context(settings_obj, branding_form=form),
            )

        messages.error(request, "Unknown settings section.")
        return redirect("admin_settings")

    return render(request, "admin_portal/settings.html", _settings_context(settings_obj))


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
        # Surface the admin's request_info question to the requester as a
        # highlighted chat message (the transition alone only logs the note).
        if action == "request_info":
            post_info_request(ticket, request.user, data.get("message", ""))
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


@require_POST
@role_required("admin")
def admin_post_message(request, pk):
    """Post a chat message on any ticket (admin), then return to the dashboard."""
    ticket = get_object_or_404(Ticket, pk=pk)
    try:
        post_ticket_message(ticket, request.user, request.POST.get("body", ""))
        messages.success(request, f"Message sent on {ticket.reference}.")
    except ChatError as exc:
        messages.error(request, str(exc))
    return redirect("admin_dashboard")
