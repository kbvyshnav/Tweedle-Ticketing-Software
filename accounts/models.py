from django.contrib.auth.models import AbstractUser
from django.db import models


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

    def __str__(self):
        return f"{self.get_username()} ({self.get_role_display()})"
