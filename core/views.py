"""Core auth-routing views (Phase 3a)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

# Maps accounts.CustomUser.role -> the URL name of that role's portal landing.
ROLE_LANDING = {
    "admin": "admin_dashboard",
    "client": "client_dashboard",
    "developer": "dev:dashboard",
    "tester": "tester:dashboard",
    "subuser": "subuser:dashboard",
}


@login_required
def post_login_redirect(request):
    """LOGIN_REDIRECT_URL target: bounce each user to their portal by role."""
    landing = ROLE_LANDING.get(request.user.role)
    if landing is None:
        raise PermissionDenied(f"No portal for role '{request.user.role}'.")
    return redirect(reverse(landing))


def root(request):
    """Bare "/": anonymous -> login; authenticated -> the redirect hub."""
    if request.user.is_authenticated:
        return redirect("post_login_redirect")
    return redirect("account_login")
