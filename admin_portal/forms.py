import re

from django import forms
from django.contrib.auth import get_user_model

from accounts.models import Client

User = get_user_model()


def generate_unique_username(full_name):
    """Build a unique, readable username from a full name (e.g. "Arjun Menon"
    -> "arjun_m", then "arjun_m2" if taken)."""
    words = re.sub(r"[^a-zA-Z\s]", "", full_name or "").strip().split()
    base = words[0].lower() if words else "user"
    if len(words) > 1:
        base += "_" + words[1][0].lower()
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


class ClientOnboardForm(forms.ModelForm):
    """Onboard a new client organisation from the admin Clients page.

    Creates the Client *organisation* record only — provisioning the client's
    login account is handled separately in the user-management flow.
    """

    class Meta:
        model = Client
        fields = [
            "name", "code", "country", "industry", "website",
            "contact_name", "contact_job_title", "contact_email",
            "contact_phone", "notes", "status",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Company name, code, country, contact name + email are required;
        # everything else is optional (matches the onboard modal's * marks).
        for name, field in self.fields.items():
            field.required = name in {
                "name", "code", "country", "contact_name", "contact_email",
            }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code.isalnum():
            raise forms.ValidationError(
                "Client code must be letters/numbers only (e.g. GMEC)."
            )
        return code


class TeamMemberForm(forms.Form):
    """Add a developer or tester from the admin Team page.

    Creates a real login account. Email delivery is console-only today, so the
    admin sets a temporary password the member can change after first login.
    """

    ROLE_CHOICES = [("developer", "Developer"), ("tester", "Tester")]

    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    is_active = forms.BooleanField(required=False, initial=True)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def save(self):
        data = self.cleaned_data
        words = data["full_name"].strip().split()
        first = words[0] if words else ""
        last = " ".join(words[1:]) if len(words) > 1 else ""
        return User.objects.create_user(
            username=generate_unique_username(data["full_name"]),
            email=data["email"],
            password=data["password"],
            role=data["role"],
            first_name=first,
            last_name=last,
            is_active=data.get("is_active", False),
        )
