from django.http import HttpResponse
from django.views import View

from core.auth import RoleRequiredMixin


class DeveloperDashboardView(RoleRequiredMixin, View):
    """Placeholder developer portal landing (real template wired in Phase 4)."""

    allowed_roles = {"developer"}

    def get(self, request):
        return HttpResponse("Developer portal — dashboard (placeholder)")
