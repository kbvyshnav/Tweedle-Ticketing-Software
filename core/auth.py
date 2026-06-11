"""Role-based access control helpers (Phase 3a).

Roles live on accounts.CustomUser.role: admin, client, subuser, developer,
tester. Unauthenticated access redirects to login; an authenticated user with
the wrong role gets a 403 (PermissionDenied).
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict a class-based view to users whose role is in `allowed_roles`.

    LoginRequiredMixin handles anonymous users (redirect to login); this adds
    the role check on top, raising PermissionDenied for the wrong role.
    """

    allowed_roles: set = set()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()  # -> redirect to login
        if request.user.role not in self.allowed_roles:
            raise PermissionDenied(
                f"Role '{request.user.role}' may not access this portal."
            )
        return super().dispatch(request, *args, **kwargs)


def role_required(*roles):
    """Function-view decorator: allow only the listed roles.

    Anonymous -> redirect to login; authenticated wrong role -> 403.
    """

    allowed = set(roles)

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in allowed:
                raise PermissionDenied(
                    f"Role '{request.user.role}' may not access this view."
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
