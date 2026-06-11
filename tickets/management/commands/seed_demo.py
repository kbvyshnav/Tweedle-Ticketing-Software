"""Seed a realistic demo dataset so every dashboard tab/badge has data.

Usage:
    python manage.py seed_demo            # idempotent: creates if absent
    python manage.py seed_demo --flush    # clears demo tickets/events/notifs
                                          # and demo users/clients, then reseeds

Safety:
- Users & Clients are upserted on a stable key (username / code).
- Tickets/TicketEvents/Notifications are only created when none exist, unless
  --flush is passed (which clears them first). The admin superuser is NEVER
  deleted (we only delete the known demo usernames).
- No model validation is bypassed: every ticket is created with a state that
  satisfies the sub_status-iff-in_progress CheckConstraint.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from accounts.models import Client
from notifications.models import Notification
from tickets.models import Ticket, TicketEvent
from tickets.transitions import transition

User = get_user_model()
S = Ticket.Status
SS = Ticket.SubStatus

DEMO_PASSWORD = "TweedleDemo!2026"
DEMO_USERNAMES = ["demo_admin", "demo_dev", "demo_tester", "demo_client", "demo_subuser"]
DEMO_CODES = ["GMEC", "INTC"]


class Command(BaseCommand):
    help = "Populate a demo dataset (users, clients, tickets covering every state)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete demo tickets/events/notifications + demo users/clients first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        users = self._seed_users()
        clients = self._seed_clients()
        # Re-link client/subuser to their org now that both exist.
        users["client"].client = clients["GMEC"]
        users["client"].save(update_fields=["client"])
        users["subuser"].client = clients["GMEC"]
        users["subuser"].save(update_fields=["client"])

        if Ticket.objects.exists():
            self.stdout.write(self.style.WARNING(
                "Tickets already present — skipping ticket seed "
                "(pass --flush to reset)."
            ))
        else:
            self._seed_tickets(users, clients)

        self._report(users, clients)

    # ── flush ────────────────────────────────────────────────────────────
    def _flush(self):
        Notification.objects.all().delete()
        TicketEvent.objects.all().delete()
        Ticket.objects.all().delete()
        # Never touch the admin superuser — only the known demo usernames.
        User.objects.filter(username__in=DEMO_USERNAMES).delete()
        Client.objects.filter(code__in=DEMO_CODES).delete()
        self.stdout.write(self.style.WARNING("Flushed demo data."))

    # ── users ────────────────────────────────────────────────────────────
    def _make_user(self, username, role, client=None):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@tweedle.local", "role": role},
        )
        user.email = f"{username}@tweedle.local"
        user.role = role
        user.client = client
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def _seed_users(self):
        return {
            "admin": self._make_user("demo_admin", "admin"),
            "developer": self._make_user("demo_dev", "developer"),
            "tester": self._make_user("demo_tester", "tester"),
            "client": self._make_user("demo_client", "client"),
            "subuser": self._make_user("demo_subuser", "subuser"),
        }

    # ── clients ──────────────────────────────────────────────────────────
    def _seed_clients(self):
        out = {}
        for name, code in [("Globomantics", "GMEC"), ("Initech", "INTC")]:
            org, _ = Client.objects.get_or_create(code=code, defaults={"name": name})
            org.name = name
            org.save()
            out[code] = org
        return out

    # ── tickets ──────────────────────────────────────────────────────────
    def _make(self, subject, status, sub_status=None, *, requester, org,
              dev=None, tester=None, paused=None, priority="medium",
              category="", accepted_by=None, accepted_at=None, closed_at=None,
              subuser_confirmed=False):
        return Ticket.objects.create(
            subject=subject,
            description=f"Demo ticket: {subject}.",
            category=category,
            priority=priority,
            requester=requester,
            client=org,
            assigned_developer=dev,
            assigned_tester=tester,
            status=status,
            sub_status=sub_status,
            paused_sub_status=paused,
            accepted_by=accepted_by,
            accepted_at=accepted_at,
            closed_at=closed_at,
            subuser_confirmed=subuser_confirmed,
        )

    def _seed_tickets(self, users, clients):
        admin = users["admin"]
        dev = users["developer"]
        tester = users["tester"]
        client = users["client"]
        subuser = users["subuser"]
        gmec = clients["GMEC"]
        intc = clients["INTC"]
        now = timezone.now()

        # ---- Static tickets, one+ per state (constraint-respecting) --------
        # new
        self._make("Cannot reset my password", S.NEW, requester=client, org=gmec,
                   priority="high", category="Bug")
        self._make("Request: export to CSV", S.NEW, requester=subuser, org=gmec,
                   priority="low", category="Feature")

        # in_progress · development
        self._make("Dashboard chart not loading", S.IN_PROGRESS, SS.DEVELOPMENT,
                   requester=client, org=gmec, dev=dev, priority="high",
                   category="Bug")
        self._make("Add dark mode toggle", S.IN_PROGRESS, SS.DEVELOPMENT,
                   requester=subuser, org=gmec, dev=dev, category="Feature")

        # in_progress · testing  (tester required)
        self._make("Invoice PDF formatting", S.IN_PROGRESS, SS.TESTING,
                   requester=client, org=intc, dev=dev, tester=tester)

        # in_progress · returned (tester required)
        self._make("Login throttling regression", S.IN_PROGRESS, SS.RETURNED,
                   requester=client, org=gmec, dev=dev, tester=tester,
                   priority="high")

        # in_progress · ready_for_uat (no tester path)
        self._make("Email template typo fix", S.IN_PROGRESS, SS.READY_FOR_UAT,
                   requester=client, org=gmec, dev=dev)

        # awaiting_client (sub_status null; paused stage stashed)
        self._make("Need account number to proceed", S.AWAITING_CLIENT,
                   requester=client, org=gmec, dev=dev, paused=SS.DEVELOPMENT,
                   category="Bug")

        # uat (one plain, one with sub-user confirmed)
        self._make("New report layout for review", S.UAT, requester=client,
                   org=gmec, dev=dev)
        self._make("Mobile nav fix to verify", S.UAT, requester=subuser,
                   org=gmec, dev=dev, subuser_confirmed=True)

        # resolved
        self._make("Slow search — optimized", S.RESOLVED, requester=client,
                   org=intc, dev=dev, accepted_by=client, accepted_at=now)

        # closed
        self._make("Broken footer link", S.CLOSED, requester=client, org=gmec,
                   dev=dev, closed_at=now)

        # rejected
        self._make("Duplicate of GMEC ticket", S.REJECTED, requester=subuser,
                   org=gmec, priority="low")

        # cancelled
        self._make("Withdrawn enhancement request", S.CANCELLED, requester=client,
                   org=intc)

        # ---- Engine-driven ticket: full history -> ends CLOSED -------------
        t = self._make("Payment webhook retries", S.NEW, requester=client,
                       org=gmec, priority="high", category="Bug")
        transition(t, "assign", admin, developer=dev, tester=tester)
        transition(t, "submit_for_testing", dev)
        transition(t, "fail", tester, failure_notes="Retries fire twice on 500s.")
        transition(t, "resubmit_for_testing", dev)
        transition(t, "pass", tester)
        transition(t, "send_to_uat", admin)
        transition(t, "approve", client)
        transition(t, "close", admin)

        # ---- Engine-driven ticket: no-tester path -> ends UAT --------------
        t2 = self._make("Onboarding tooltip copy", S.NEW, requester=subuser,
                        org=gmec, category="Feature")
        transition(t2, "assign", admin, developer=dev)
        transition(t2, "mark_ready", dev)
        transition(t2, "send_to_uat", admin)

        self.stdout.write(self.style.SUCCESS("Seeded tickets."))

    # ── report ───────────────────────────────────────────────────────────
    def _report(self, users, clients):
        out = self.stdout
        out.write("")
        out.write(self.style.MIGRATE_HEADING("=== Demo data summary ==="))
        out.write(f"Clients: {Client.objects.count()}  "
                  f"(codes: {', '.join(DEMO_CODES)})")
        out.write(f"Users (non-superuser demo): {len(users)}  "
                  f"| password (all): {DEMO_PASSWORD}")
        for key, u in users.items():
            org = u.client.code if u.client_id else "-"
            out.write(f"  - {u.username:14} role={u.role:9} org={org}")

        out.write("")
        out.write(f"Tickets total: {Ticket.objects.count()}")
        out.write(f"TicketEvents:  {TicketEvent.objects.count()}   "
                  f"Notifications: {Notification.objects.count()}")
        out.write("Per status / sub_status:")
        rows = (Ticket.objects
                .values("status", "sub_status")
                .annotate(n=Count("id"))
                .order_by("status", "sub_status"))
        for r in rows:
            sub = r["sub_status"] or "-"
            out.write(f"  {r['status']:16} {sub:14} {r['n']}")
        out.write(self.style.SUCCESS("Done."))
