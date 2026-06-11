from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "action", "ticket", "actor", "is_read", "created_at")
    list_filter = ("is_read", "action")
    search_fields = ("recipient__username", "message", "ticket__reference")
    date_hierarchy = "created_at"
