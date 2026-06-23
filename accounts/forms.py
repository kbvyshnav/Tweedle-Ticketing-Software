from django import forms

from .models import CustomUser


class ProfileForm(forms.ModelForm):
    """Edit your own identity fields (name + email). Username/role are fixed."""

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Email is the alternate login identifier, so require it here even though
        # AbstractUser leaves it optional at the model level.
        self.fields["email"].required = True

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")
        if (
            CustomUser.objects.exclude(pk=self.instance.pk)
            .filter(email__iexact=email)
            .exists()
        ):
            raise forms.ValidationError("That email is already in use by another account.")
        return email
