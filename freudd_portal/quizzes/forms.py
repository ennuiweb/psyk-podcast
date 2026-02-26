"""Forms used by auth pages."""

from __future__ import annotations

import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

USERNAME_CLEAN_RE = re.compile(r"[^A-Za-z0-9@.+_-]+")


class SignupForm(UserCreationForm):
    username = forms.CharField(required=False, max_length=150)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_username(self) -> str:
        return str(self.cleaned_data.get("username") or "").strip()

    def clean_email(self) -> str:
        return str(self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        username = str(cleaned.get("username") or "").strip()
        email = str(cleaned.get("email") or "").strip().lower()
        if not username and email:
            generated = self._generate_username_from_email(email)
            cleaned["username"] = generated
            self.cleaned_data["username"] = generated
        return cleaned

    def _generate_username_from_email(self, email: str) -> str:
        local_part = email.split("@", 1)[0].strip().lower()
        normalized = USERNAME_CLEAN_RE.sub("-", local_part).strip("-_.")
        seed = normalized or "user"

        max_length = int(User._meta.get_field("username").max_length or 150)
        seed = seed[:max_length]
        if not User.objects.filter(username=seed).exists():
            return seed

        for index in range(2, 1000):
            suffix = f"-{index}"
            trimmed_seed = seed[: max_length - len(suffix)] or "user"
            candidate = f"{trimmed_seed}{suffix}"
            if not User.objects.filter(username=candidate).exists():
                return candidate

        raise forms.ValidationError(
            "Kunne ikke generere et brugernavn automatisk. Udfyld brugernavn manuelt."
        )
