from django.views.generic import TemplateView

from core.auth import RoleRequiredMixin


class AdminDashboardView(RoleRequiredMixin, TemplateView):
    """Admin portal dashboard.

    Phase 4.0: renders the converted dashboard template (extends base.html).
    Still RoleRequired(admin); live data + button wiring come in later steps.
    """

    allowed_roles = {"admin"}
    template_name = "admin_portal/dashboard.html"
