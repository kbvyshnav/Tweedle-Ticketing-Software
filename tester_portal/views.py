from django.http import HttpResponse
from django.views import View

from core.auth import RoleRequiredMixin


class TesterDashboardView(RoleRequiredMixin, View):
    """Placeholder tester portal landing (real template wired in Phase 4)."""

    allowed_roles = {"tester"}

    def get(self, request):
        return HttpResponse("Tester portal — dashboard (placeholder)")
