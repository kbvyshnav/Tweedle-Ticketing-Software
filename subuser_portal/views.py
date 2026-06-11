from django.http import HttpResponse
from django.views import View

from core.auth import RoleRequiredMixin


class SubuserDashboardView(RoleRequiredMixin, View):
    """Placeholder sub-user portal landing (real template wired in Phase 4)."""

    allowed_roles = {"subuser"}

    def get(self, request):
        return HttpResponse("Sub-user portal — dashboard (placeholder)")
