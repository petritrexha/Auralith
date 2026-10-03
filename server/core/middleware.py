from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Until a user replaces the admin-issued temp password, every page redirects to /app/first-login."""

    ALLOWED_PREFIXES = ("/app/first-login", "/logout", "/static/", "/api/", "/healthz")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not request.path.startswith(self.ALLOWED_PREFIXES):
            profile = getattr(user, "profile", None)
            if profile is not None and profile.must_change_password:
                return redirect(reverse("first-login"))
        return self.get_response(request)
