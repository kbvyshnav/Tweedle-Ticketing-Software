"""Email-on-notification signal.

Every in-app Notification (from the transition engine, the chat helper, or
ticket creation) triggers a best-effort email — but only AFTER the surrounding
database transaction commits, via transaction.on_commit(). That guarantees we
never email about a rolled-back action and a mail outage can't roll back the
ticket change that produced the notification.
"""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .email import email_for_notification
from .models import Notification


@receiver(post_save, sender=Notification, dispatch_uid="notifications.email_on_create")
def email_on_notification(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    transaction.on_commit(lambda: email_for_notification(instance))
