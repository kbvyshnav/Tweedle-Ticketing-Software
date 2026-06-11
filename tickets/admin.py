from django.contrib import admin

from .models import Ticket, TicketAttachment, TicketEvent, TicketMessage


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "subject",
        "status",
        "sub_status",
        "requester",
        "assigned_developer",
        "assigned_tester",
        "created_at",
    )
    list_filter = ("status", "sub_status", "priority")
    search_fields = ("reference", "subject")
    date_hierarchy = "created_at"


@admin.register(TicketEvent)
class TicketEventAdmin(admin.ModelAdmin):
    """Immutable audit log — inspect-only in the admin."""

    list_display = (
        "ticket",
        "actor",
        "action",
        "from_status",
        "from_sub_status",
        "to_status",
        "to_sub_status",
        "created_at",
    )
    list_filter = ("action", "to_status")
    search_fields = ("ticket__reference", "action")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "created_at")
    search_fields = ("ticket__reference", "body")


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("ticket", "uploaded_by", "file", "created_at")
    search_fields = ("ticket__reference",)
