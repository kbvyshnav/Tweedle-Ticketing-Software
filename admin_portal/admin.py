from django.contrib import admin

from .models import OrganisationSettings


@admin.register(OrganisationSettings)
class OrganisationSettingsAdmin(admin.ModelAdmin):
    list_display = ("org_name", "default_priority", "powered_by_tweedle", "updated_at")
