from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser


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
