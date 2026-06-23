from django import forms

from accounts.models import Client


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
