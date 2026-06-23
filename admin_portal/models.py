from django.db import models

# Email-notification events shown in the Settings → Email Notifications table.
# Each event has two audiences (admin / assignee); both default to enabled.
# Order here is the order rendered in the table.
NOTIFICATION_EVENTS = [
    ("new_ticket", "New ticket received"),
    ("assigned", "Ticket assigned to developer / tester"),
    ("reassigned", "Ticket reassigned"),
    ("ready_for_test", "Developer marks ticket ready for testing"),
    ("tester_verdict", "Tester passes or fails a ticket"),
    ("client_response", "Client responds to awaiting-client request"),
    ("closed", "Ticket closed"),
    ("overdue", "Ticket overdue (24-hour warning)"),
]


class OrganisationSettings(models.Model):
    """Singleton row holding the admin Settings page values.

    There is exactly one organisation per deployment for now, so this is a
    classic singleton (always `pk=1`) loaded via `OrganisationSettings.load()`.
    Notification toggles are stored as a small JSON map (`<event>_admin` /
    `<event>_assignee` -> bool) so adding an event needs no migration; absent
    keys default to enabled (`notification_rows()` applies that default).
    """

    class Priority(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    org_name = models.CharField(max_length=200, default="Tweedle Demo Org")
    industry = models.CharField(max_length=120, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    default_priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM
    )
    logo = models.FileField(upload_to="branding/", blank=True, null=True)
    powered_by_tweedle = models.BooleanField(default=True)
    notification_prefs = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organisation settings"
        verbose_name_plural = "Organisation settings"

    def __str__(self):
        return self.org_name

    @classmethod
    def load(cls):
        """Return the single settings row, creating it with defaults if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def notification_rows(self):
        """Event rows for the template, each with its current admin/assignee state.

        Missing keys default to enabled so a freshly created row (empty JSON)
        renders every toggle on — matching the original static design.
        """
        prefs = self.notification_prefs or {}
        return [
            {
                "key": key,
                "label": label,
                "admin": prefs.get(f"{key}_admin", True),
                "assignee": prefs.get(f"{key}_assignee", True),
            }
            for key, label in NOTIFICATION_EVENTS
        ]
