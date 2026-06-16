from django import forms

from tickets.models import Ticket

CATEGORY_CHOICES = [
    ("", "Select a category"),
    ("Bug", "Bug"),
    ("Feature", "Feature"),
    ("Billing", "Billing"),
    ("Access Control", "Access Control"),
    ("Reports", "Reports"),
    ("Integration", "Integration"),
    ("UI/UX", "UI/UX"),
    ("Performance", "Performance"),
    ("Other", "Other"),
]

PRIORITY_CHOICES = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
]


class TicketSubmitForm(forms.Form):
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "id": "subjectInput",
            "class": "tw-input",
            "placeholder": "Brief summary of your issue",
            "maxlength": "160",
        }),
    )
    description = forms.CharField(
        min_length=20,
        widget=forms.Textarea(attrs={
            "id": "descTextarea",
            "class": "tw-textarea",
            "rows": "7",
            "placeholder": "e.g. When I click Export on the Reports page, the download starts but the file is empty…",
            "style": "resize:vertical;min-height:160px;",
        }),
    )
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            "id": "categorySelect",
            "class": "tw-select",
        }),
    )
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        initial="medium",
        widget=forms.Select(attrs={
            "id": "prioritySelect",
            "class": "tw-select",
        }),
    )

    def clean_category(self):
        val = self.cleaned_data.get("category", "")
        if not val:
            raise forms.ValidationError("Please select a category.")
        return val
