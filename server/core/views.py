"""Web pages. Kept intentionally simple (server-rendered templates) so the UI team can restyle freely.

Rule of thumb: every member query is filtered by request.user; every /manage view is staff-only.
"""
from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.agent.llm import ai_mode
from core.agent.reporter import generate_report
from core.forms import CreateUserForm, EditUserForm, SettingsForm
from core.models import AnalyzeLog, Card, Concept, TeamReport, UserConcept
from core.services import accounts, insights, knowledge

User = get_user_model()


def staff_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return render(request, "403.html", status=403)
        return view(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
def landing(request):
    return render(request, "core/landing.html")


def healthz(request):
    return JsonResponse({"ok": True, "ai_mode": ai_mode()})


# ---------------------------------------------------------------------------
# Member
# ---------------------------------------------------------------------------
@login_required
def first_login(request):
    profile = knowledge.get_profile(request.user)
    if request.method == "POST":
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            profile.must_change_password = False
            profile.save(update_fields=["must_change_password"])
            messages.success(request, "Password updated. Welcome to LearnLoop!")
            return redirect("app-setup")
    else:
        form = SetPasswordForm(request.user)
    return render(request, "core/first_login.html", {"form": form})


@login_required
def app_home(request):
    data = insights.member_insights(request.user)
    latest = Card.objects.filter(user=request.user).select_related("concept")[:3]
    return render(request, "core/dashboard.html", {"i": data, "latest": latest})


@login_required
def member_insights_json(request):
    return JsonResponse(insights.member_insights(request.user), json_dumps_params={"default": str})


@login_required
def card_list(request):
    cards = Card.objects.filter(user=request.user).select_related("concept")
    category = request.GET.get("category", "")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    if category:
        cards = cards.filter(concept__category=category)
    if status == "unread":
        cards = cards.filter(read_at__isnull=True)
    elif status == "saved":
        cards = cards.filter(saved=True)
    if q:
        cards = cards.filter(Q(concept__name__icontains=q) | Q(summary__icontains=q) | Q(file_path__icontains=q))
    page = Paginator(cards, 12).get_page(request.GET.get("page"))
    return render(request, "core/card_list.html", {
        "page": page, "categories": Concept.Category.choices, "category": category, "status": status, "q": q,
    })


@login_required
def card_detail(request, pk: int):
    card = get_object_or_404(Card.objects.select_related("concept"), pk=pk, user=request.user)
    if card.read_at is None:
        card.read_at = timezone.now()
        card.save(update_fields=["read_at"])
    uc = UserConcept.objects.filter(user=request.user, concept=card.concept).first()
    return render(request, "core/card_detail.html", {"card": card, "uc": uc})


@login_required
@require_POST
def card_action(request, pk: int):
    card = get_object_or_404(Card, pk=pk, user=request.user)
    action = request.POST.get("action")
    if action == "known":
        knowledge.set_status(request.user, card.concept, UserConcept.Status.KNOWN)
        messages.success(request, f"Nice — {card.concept.name} marked as known. We won't explain it again.")
    elif action == "mute":
        knowledge.set_status(request.user, card.concept, UserConcept.Status.MUTED)
        messages.info(request, f"{card.concept.name} muted.")
    elif action in ("save", "unsave"):
        card.saved = action == "save"
        card.save(update_fields=["saved"])
    nxt = request.POST.get("next", "")
    if nxt.startswith("/app/"):  # only allow local redirects
        return redirect(nxt)
    return redirect("card-detail", pk=pk)


@login_required
@require_POST
def concept_action(request, slug: str):
    concept = get_object_or_404(Concept, slug=slug)
    status = request.POST.get("status")
    if status in {s.value for s in UserConcept.Status}:
        knowledge.set_status(request.user, concept, status)
    return redirect("concepts")


@login_required
def concepts(request):
    rows = UserConcept.objects.filter(user=request.user).select_related("concept").order_by("concept__category", "concept__name")
    grouped: dict[str, list] = {}
    for uc in rows:
        grouped.setdefault(uc.concept.get_category_display(), []).append(uc)
    counts = {s: rows.filter(status=s).count() for s in UserConcept.Status.values}
    return render(request, "core/concepts.html", {"grouped": grouped, "counts": counts})


@login_required
def setup(request):
    profile = knowledge.get_profile(request.user)
    new_token = request.session.pop("new_token", None)
    last_ping = cache.get(f"ll:lastping:{request.user.pk}")
    return render(request, "core/setup.html", {
        "profile": profile, "new_token": new_token, "last_ping": last_ping,
        "server_url": request.build_absolute_uri("/").rstrip("/"),
    })


@login_required
def setup_status(request):
    """Polled by the 'Test connection' button. The plugin pings on session start and on every flush."""
    last_ping = cache.get(f"ll:lastping:{request.user.pk}")
    last_log = AnalyzeLog.objects.filter(user=request.user).first()
    connected = bool(last_ping and (timezone.now() - last_ping).total_seconds() < 15 * 60)
    return JsonResponse({
        "connected": connected,
        "last_ping": last_ping.isoformat() if last_ping else None,
        "last_analyze": last_log.created_at.isoformat() if last_log else None,
    })


@login_required
@require_POST
def regenerate_token(request):
    raw = knowledge.get_profile(request.user).regenerate_token()
    request.session["new_token"] = raw
    messages.success(request, "New token created. Copy it now — it won't be shown again. Update LEARNLOOP_TOKEN.")
    return redirect("app-setup")


@login_required
def user_settings(request):
    profile = knowledge.get_profile(request.user)
    form = SettingsForm(request.POST or None, instance=profile, prefix="s")
    pw_form = SetPasswordForm(request.user, request.POST or None, prefix="pw")
    if request.method == "POST":
        if "save_settings" in request.POST and form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("app-settings")
        if "change_password" in request.POST and pw_form.is_valid():
            pw_form.save()
            update_session_auth_hash(request, pw_form.user)
            messages.success(request, "Password changed.")
            return redirect("app-settings")
    return render(request, "core/settings.html", {"form": form, "pw_form": pw_form})


# ---------------------------------------------------------------------------
# Admin (/manage)
# ---------------------------------------------------------------------------
@staff_required
def manage_home(request):
    return render(request, "core/manage_home.html", {
        "o": insights.org_insights(), "report": TeamReport.objects.first(), "ai_mode": ai_mode(),
        "mastery_history": TeamReport.objects.filter(data__has_key="org_mastery_rate")[:8],
    })


@staff_required
def org_insights_json(request):
    return JsonResponse(insights.org_insights(int(request.GET.get("days", 30))), json_dumps_params={"default": str})


@staff_required
def manage_users(request):
    users = User.objects.select_related("profile").annotate(
        cards_received=Count("cards", distinct=True),
        mastered=Count("user_concepts", filter=Q(user_concepts__status=UserConcept.Status.KNOWN), distinct=True),
    ).order_by("email")
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")
    if q:
        users = users.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if role:
        users = users.filter(is_staff=(role == "admin"))
    if status:
        users = users.filter(is_active=(status == "active"))
    return render(request, "core/manage_users.html", {"users": users, "q": q, "role": role, "status": status})


@staff_required
def manage_user_new(request):
    form = CreateUserForm(request.POST or None)
    created = None
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            user, password, token = accounts.create_member(
                email=d["email"], full_name=d["full_name"], is_admin=d["role"] == "admin",
                password=d["temp_password"] or None, skill_level=d["skill_level"],
            )
            created = {"user": user, "password": password, "token": token}
            form = CreateUserForm()
        except ValueError as exc:
            form.add_error("email", str(exc))
    return render(request, "core/manage_user_new.html", {"form": form, "created": created})


@staff_required
def manage_user_detail(request, pk: int):
    target = get_object_or_404(User.objects.select_related("profile"), pk=pk)
    profile = knowledge.get_profile(target)
    secret = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit":
            form = EditUserForm(request.POST)
            if form.is_valid():
                d = form.cleaned_data
                target.first_name, _, target.last_name = d["full_name"].partition(" ")
                if target != request.user:  # don't let an admin demote themselves by accident
                    target.is_staff = target.is_superuser = d["role"] == "admin"
                target.save()
                profile.skill_level, profile.daily_card_limit = d["skill_level"], d["daily_card_limit"]
                profile.save()
                messages.success(request, "User updated.")
        elif action == "toggle_active" and target != request.user:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            messages.info(request, "User enabled." if target.is_active else "User disabled — their plugin token stopped working.")
        elif action == "reset_password":
            secret = {"label": "Temporary password", "value": accounts.reset_password(target)}
        elif action == "regenerate_token":
            secret = {"label": "New plugin token", "value": profile.regenerate_token()}
    form = EditUserForm(initial={
        "full_name": target.get_full_name(), "role": "admin" if target.is_staff else "member",
        "skill_level": profile.skill_level, "daily_card_limit": profile.daily_card_limit,
    })
    return render(request, "core/manage_user_detail.html", {
        "target": target, "profile": profile, "form": form, "secret": secret,
        "i": insights.member_insights(target),
        "hotspots": insights.comprehension_hotspots(user=target, limit=5),
        "concepts": UserConcept.objects.filter(user=target).select_related("concept").order_by("-last_seen")[:50],
    })


@staff_required
def manage_concepts(request):
    rows = Concept.objects.annotate(
        exposed=Count("user_concepts", distinct=True),
        mastered=Count("user_concepts", filter=Q(user_concepts__status=UserConcept.Status.KNOWN), distinct=True),
    ).filter(exposed__gt=0).order_by("-exposed", "name")
    for r in rows:
        r.mastery_rate = int(100 * r.mastered / r.exposed) if r.exposed else 0
    return render(request, "core/manage_concepts.html", {"rows": rows})


@staff_required
def manage_reports(request):
    if request.method == "POST":
        report = generate_report(created_by=request.user, days=int(request.POST.get("days", 7)))
        messages.success(request, "Briefing generated.")
        return redirect("manage-report", pk=report.pk)
    return render(request, "core/manage_reports.html", {"reports": TeamReport.objects.all()[:30]})


@staff_required
def manage_report(request, pk: int):
    return render(request, "core/manage_report.html", {"report": get_object_or_404(TeamReport, pk=pk)})


@staff_required
def manage_activity(request):
    """The agent's decision trace per /analyze call — the 'show me it's agentic' page for demos."""
    logs = AnalyzeLog.objects.select_related("user")[:50]
    return render(request, "core/manage_activity.html", {"logs": logs})
