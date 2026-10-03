from django import forms
from django.contrib.auth.forms import AuthenticationForm

from core.models import Profile


class EmailLoginForm(AuthenticationForm):
    """Users log in with their email (stored as the username). Errors stay generic."""

    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))
    error_messages = {
        "invalid_login": "Email or password is incorrect.",
        "inactive": "Email or password is incorrect.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class CreateUserForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=[("member", "Member"), ("admin", "Admin")])
    skill_level = forms.ChoiceField(choices=Profile.Skill.choices)
    temp_password = forms.CharField(required=False, help_text="Leave empty to auto-generate.")


class EditUserForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=[("member", "Member"), ("admin", "Admin")])
    skill_level = forms.ChoiceField(choices=Profile.Skill.choices)
    daily_card_limit = forms.IntegerField(min_value=0, max_value=50)


class CardStyleForm(forms.ModelForm):
    """Personalize page: how cards are written and shown."""

    class Meta:
        model = Profile
        fields = ["explanation_depth", "show_diagrams", "use_analogies", "terminal_detail"]
        widgets = {
            "explanation_depth": forms.RadioSelect,
            "terminal_detail": forms.RadioSelect,
        }


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["skill_level", "daily_card_limit"]
        widgets = {"daily_card_limit": forms.NumberInput(attrs={"min": 0, "max": 50})}
