"""Account creation and admin actions. Accounts are only ever created by admins."""
from __future__ import annotations

import secrets
import string

from django.contrib.auth import get_user_model
from django.db import transaction

from core.models import Profile

User = get_user_model()


def generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "-_!"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


@transaction.atomic
def create_member(
    *, email: str, full_name: str = "", is_admin: bool = False, password: str | None = None,
    skill_level: str = "beginner", must_change_password: bool = True,
) -> tuple[User, str, str]:
    """Create a user + profile + plugin token. Returns (user, temp_password, raw_token) — show both ONCE."""
    email = email.strip().lower()
    if User.objects.filter(username=email).exists():
        raise ValueError("A user with this email already exists.")
    first, _, last = full_name.strip().partition(" ")
    password = password or generate_temp_password()
    user = User.objects.create_user(username=email, email=email, password=password, first_name=first, last_name=last)
    user.is_staff = is_admin
    user.is_superuser = is_admin
    user.save()
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.skill_level = skill_level
    profile.must_change_password = must_change_password
    profile.save()
    raw_token = profile.regenerate_token()
    user.profile = profile  # make sure callers see the profile that holds the token
    return user, password, raw_token


def reset_password(user) -> str:
    pw = generate_temp_password()
    user.set_password(pw)
    user.save(update_fields=["password"])
    Profile.objects.filter(user=user).update(must_change_password=True)
    return pw
