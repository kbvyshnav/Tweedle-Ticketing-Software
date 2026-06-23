"""Ticket attachment upload: one shared field + save helper.

Both the client and sub-user submit forms attach files the same way, so the
validation rules (count / size / type) and the row-creation step live here in
one place — mirroring how `tickets/chat.py` centralises message posting.
"""

import os

from django import forms

# Upload limits — kept in sync with the copy shown in the submit-page UI
# ("Up to 3 files … PDF, DOC, DOCX, PNG, JPG — Max 10MB").
MAX_ATTACHMENTS = 3
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB per file
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
ALLOWED_LABEL = "PDF, DOC, DOCX, PNG, JPG"


class MultipleFileInput(forms.ClearableFileInput):
    """File widget that accepts more than one file (Django 5 opt-in)."""

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A ``FileField`` that cleans a *list* of uploaded files.

    Django's stock ``FileField`` only validates a single upload; this runs the
    per-file clean across every file the multi-select widget submitted.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [single_clean(item, initial) for item in data]


class AttachmentsField(MultipleFileField):
    """Optional ticket-attachments field with Tweedle's count/size/type rules."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = super().clean(data, initial)
        if len(files) > MAX_ATTACHMENTS:
            raise forms.ValidationError(
                f"You can attach at most {MAX_ATTACHMENTS} files."
            )
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise forms.ValidationError(
                    f"“{f.name}” is not an allowed file type. "
                    f"Allowed types: {ALLOWED_LABEL}."
                )
            if f.size > MAX_ATTACHMENT_SIZE:
                raise forms.ValidationError(
                    f"“{f.name}” is larger than 10 MB."
                )
        return files


def save_attachments(ticket, files, user):
    """Create one ``TicketAttachment`` per uploaded file (no-op if none)."""
    from .models import TicketAttachment

    return [
        TicketAttachment.objects.create(ticket=ticket, uploaded_by=user, file=f)
        for f in (files or [])
    ]
