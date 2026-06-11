from django.http import HttpResponse
from django.views import View

from core.auth import RoleRequiredMixin


class AdminDashboardView(RoleRequiredMixin, View):
    """Placeholder admin portal landing (real template wired in Phase 4)."""

    allowed_roles = {"admin"}

    def get(self, request):
        return HttpResponse("Admin portal — dashboard (placeholder)")
