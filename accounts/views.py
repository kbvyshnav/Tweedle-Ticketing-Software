from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from .forms import ProfileForm

# Each role's themed base — the profile page extends the caller's own base, the
# same way the notification feed does.
BASE_FOR_ROLE = {
    "admin": "base.html",
    "client": "client_base.html",
    "subuser": "subuser_base.html",
    "developer": "developer_base.html",
    "tester": "tester_base.html",
}


@login_required
def profile(request):
    """Self-service profile page: edit own name/email + change password.

    Two independent sections (a hidden ``section`` field picks which one was
    submitted), mirroring the admin Settings page so saving one never disturbs
    the other. Shared across all five portals via a per-role base template.
    """
    user = request.user
    profile_form = ProfileForm(instance=user)
    password_form = PasswordChangeForm(user)

    if request.method == "POST":
        section = request.POST.get("section")
        if section == "profile":
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("profile")
            messages.error(request, "Please correct the highlighted fields and try again.")
        elif section == "password":
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                # Keep the user signed in after the password hash changes.
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed.")
                return redirect("profile")
            messages.error(request, "Please correct the highlighted fields and try again.")
        else:
            messages.error(request, "Unknown profile section.")
            return redirect("profile")

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "base_template": BASE_FOR_ROLE.get(user.role, "base.html"),
            "active_nav": "",
        },
    )
