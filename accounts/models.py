from django.contrib.auth.models import AbstractUser
from django.db import models


class Client(models.Model):
    """A client organisation that `client` / `subuser` users belong to.

    Lives in the accounts app because it is an identity/account concept (the
    org a user belongs to), alongside CustomUser.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        PENDING = "pending", "Pending"

    name = models.CharField(max_length=200)
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Short uppercase org code used in ticket references, e.g. GMEC.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Onboarding / profile details surfaced on the admin Clients page.
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    country = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_job_title = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class CustomUser(AbstractUser):
    """Project user with a role.

    Role values come from TARGET_TICKET_FLOW.md section 2 (the canonical
    actor list), which supersedes the legacy handoff's "user" wording:
    admin, client, subuser, developer, tester.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CLIENT = "client", "Client"
        SUBUSER = "subuser", "Sub-user"
        DEVELOPER = "developer", "Developer"
        TESTER = "tester", "Tester"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENT,
        help_text="Determines which portal and permissions the user gets.",
    )
    # Org this user belongs to; null for internal staff (admin/developer/tester).
    client = models.ForeignKey(
        "accounts.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
        help_text="Client organisation this user belongs to; null for internal staff.",
    )

    def __str__(self):
        return f"{self.get_username()} ({self.get_role_display()})"
