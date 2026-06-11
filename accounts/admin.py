from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Client, CustomUser


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Extends Django's UserAdmin so `role` is visible and editable."""

    # Show role in the changelist.
    list_display = UserAdmin.list_display + ("role",)
    list_filter = UserAdmin.list_filter + ("role",)

    # Add the role field to the edit form (after the default user info).
    fieldsets = UserAdmin.fieldsets + (
        ("Role", {"fields": ("role",)}),
    )
    # And to the "add user" form.
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Role", {"fields": ("role",)}),
    )
