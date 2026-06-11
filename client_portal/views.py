from django.http import HttpResponse
from django.views import View

from core.auth import RoleRequiredMixin


class ClientDashboardView(RoleRequiredMixin, View):
    """Placeholder client portal landing (real template wired in Phase 4)."""

    allowed_roles = {"client"}

    def get(self, request):
        return HttpResponse("Client portal — dashboard (placeholder)")
