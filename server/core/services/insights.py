"""Numbers for the member dashboard, the admin org dashboard and the reporting agent.

All functions return plain dicts/lists so they can feed templates, JSON endpoints or the agent.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import PurePosixPath

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import CHECKLIST_SLUG_PREFIX, AnalyzeLog, Card, Concept, UserConcept

User = get_user_model()
S = UserConcept.Status


def _rate(known: int, surfaced: int) -> float:
    return round(known / surfaced, 2) if surfaced else 0.0


def streak_days(user) -> int:
    """Consecutive days (ending today or yesterday) with at least one card."""
    days = set(
        Card.objects.filter(user=user).annotate(d=TruncDate("created_at")).values_list("d", flat=True).distinct()
    )
    if not days:
        return 0
    today = timezone.localdate()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def member_insights(user, days: int = 30) -> dict:
    ucs = UserConcept.objects.filter(user=user).from_work()
    surfaced = ucs.count()
    known = ucs.filter(status=S.KNOWN).count()
    verified = ucs.filter(status=S.KNOWN, verified_at__isnull=False).count()
    muted = ucs.filter(status=S.MUTED).count()
    since = timezone.now() - timedelta(days=days)

    per_day = dict(
        Card.objects.filter(user=user, created_at__gte=since)
        .annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(n=Count("id"))
        .values_list("d", "n")
    )
    today = timezone.localdate()
    cards_per_day = [
        {"date": (today - timedelta(days=i)).isoformat(), "count": per_day.get(today - timedelta(days=i), 0)}
        for i in range(days - 1, -1, -1)
    ]

    by_category = list(ucs.values("concept__category").annotate(n=Count("id")).order_by("-n"))
    keeps_showing_up = list(
        ucs.filter(seen_count__gt=1).exclude(status__in=[S.KNOWN, S.MUTED]).order_by("-seen_count")
        .values("concept__name", "concept__slug", "seen_count")[:5]
    )
    recently_learned = list(
        ucs.filter(status=S.KNOWN).order_by("-known_at").values("concept__name", "known_at")[:5]
    )
    return {
        "surfaced": surfaced,
        "known": known,
        "muted": muted,
        "mastery_rate": _rate(known, surfaced),
        "verified": verified,
        "verified_rate": _rate(verified, surfaced),
        "comprehension_debt": max(surfaced - known - muted, 0),
        "cards_total": Card.objects.filter(user=user).count(),
        "unread_cards": Card.objects.filter(user=user, read_at__isnull=True).count(),
        "cards_per_day": cards_per_day,
        "by_category": [{"category": r["concept__category"], "count": r["n"]} for r in by_category],
        "keeps_showing_up": keeps_showing_up,
        "recently_learned": recently_learned,
        "streak": streak_days(user),
    }


def comprehension_hotspots(days: int = 30, limit: int = 8, user=None) -> list[dict]:
    """Code areas (top-level dirs) where AI introduced concepts that people haven't understood yet.

    This is the 'bus factor' view a manager cares about: where would an incident hurt most?
    """
    since = timezone.now() - timedelta(days=days)
    cards = Card.objects.filter(created_at__gte=since).exclude(file_path="").select_related("concept", "user")
    if user is not None:
        cards = cards.filter(user=user)
    status_map = {
        (uc["user_id"], uc["concept_id"]): uc["status"]
        for uc in UserConcept.objects.values("user_id", "concept_id", "status")
    }
    areas: dict[str, dict] = defaultdict(lambda: {"cards": 0, "understood": 0, "people": set(), "understood_by": set(), "concepts": Counter()})
    for card in cards:
        parts = PurePosixPath(card.file_path.replace("\\", "/")).parts
        area = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if parts else "(root)")
        a = areas[area]
        a["cards"] += 1
        a["people"].add(card.user.email or card.user.username)
        a["concepts"][card.concept.name] += 1
        if status_map.get((card.user_id, card.concept_id)) == S.KNOWN:
            a["understood"] += 1
            a["understood_by"].add(card.user.email or card.user.username)
    out = []
    for area, a in areas.items():
        understood_rate = _rate(a["understood"], a["cards"])
        out.append({
            "area": area,
            "cards": a["cards"],
            "understood_rate": understood_rate,
            "people_exposed": len(a["people"]),
            "people_understanding": len(a["understood_by"]),
            "single_point_of_knowledge": len(a["understood_by"]) == 1 and len(a["people"]) > 1,
            "top_concepts": [name for name, _ in a["concepts"].most_common(3)],
            "risk_score": round(a["cards"] * (1 - understood_rate), 1),
        })
    out.sort(key=lambda r: r["risk_score"], reverse=True)
    return out[:limit]


def needs_attention(days: int = 30, limit: int = 5) -> list[dict]:
    """Members with high exposure and low mastery. Framed as support, never as a leaderboard."""
    rows = []
    for user in User.objects.filter(is_active=True):
        ucs = UserConcept.objects.filter(user=user).from_work()
        surfaced = ucs.count()
        if surfaced < 3:
            continue
        known = ucs.filter(status=S.KNOWN).count()
        rows.append({
            "user_id": user.id,
            "name": user.get_full_name() or user.email or user.username,
            "surfaced": surfaced,
            "known": known,
            "mastery_rate": _rate(known, surfaced),
            "open_concepts": list(
                ucs.exclude(status__in=[S.KNOWN, S.MUTED]).order_by("-seen_count").values_list("concept__name", flat=True)[:3]
            ),
        })
    rows.sort(key=lambda r: (r["mastery_rate"], -r["surfaced"]))
    return rows[:limit]


def org_insights(days: int = 30) -> dict:
    now = timezone.now()
    since = now - timedelta(days=days)
    ucs = UserConcept.objects.from_work()
    surfaced = ucs.count()
    known = ucs.filter(status=S.KNOWN).count()
    verified = ucs.filter(status=S.KNOWN, verified_at__isnull=False).count()
    from core.models import ComprehensionCheck  # local import keeps module import order simple
    checks = ComprehensionCheck.objects.filter(submitted_at__gte=since)

    common = list(
        Concept.objects.annotate(
            exposed=Count("user_concepts", distinct=True),
            mastered=Count("user_concepts", filter=Q(user_concepts__status=S.KNOWN), distinct=True),
        )
        .filter(exposed__gt=0)
        .exclude(slug__startswith=CHECKLIST_SLUG_PREFIX)
        .order_by("-exposed", "name")
        .values("name", "slug", "category", "exposed", "mastered")[:10]
    )
    for c in common:
        c["mastery_rate"] = _rate(c["mastered"], c["exposed"])

    categories = defaultdict(lambda: {"exposed": 0, "mastered": 0})
    for row in ucs.values("concept__category", "status"):
        cat = categories[row["concept__category"]]
        cat["exposed"] += 1
        if row["status"] == S.KNOWN:
            cat["mastered"] += 1

    logs = AnalyzeLog.objects.filter(created_at__gte=since)
    cost = logs.aggregate(calls=Sum("llm_calls"), inp=Sum("input_tokens"), out=Sum("output_tokens"))
    inp, out = cost["inp"] or 0, cost["out"] or 0
    return {
        "active_users_7d": User.objects.filter(profile__last_active_at__gte=now - timedelta(days=7)).count(),
        "active_users_30d": User.objects.filter(profile__last_active_at__gte=now - timedelta(days=30)).count(),
        "members": User.objects.filter(is_active=True).count(),
        "cards_total": Card.objects.count(),
        "cards_period": Card.objects.filter(created_at__gte=since).count(),
        "surfaced": surfaced,
        "known": known,
        "org_mastery_rate": _rate(known, surfaced),
        "verified": verified,
        "verified_rate": _rate(verified, surfaced),
        "checks": {
            "taken": checks.count(),
            "passed": checks.filter(status=ComprehensionCheck.Status.PASSED).count(),
            "needs_review": checks.filter(status=ComprehensionCheck.Status.UNVERIFIED).count(),
        },
        "comprehension_debt": ucs.exclude(status__in=[S.KNOWN, S.MUTED]).count(),
        "most_common_concepts": common,
        "by_category": [
            {"category": k, **v, "mastery_rate": _rate(v["mastered"], v["exposed"])} for k, v in sorted(categories.items())
        ],
        "needs_attention": needs_attention(days),
        "hotspots": comprehension_hotspots(days),
        "cost": {
            "llm_calls": cost["calls"] or 0,
            "input_tokens": inp,
            "output_tokens": out,
            # Haiku 4.5 list price: ~$1 / M input, ~$5 / M output. Rough estimate only.
            "approx_usd": round(inp / 1_000_000 * 1 + out / 1_000_000 * 5, 4),
        },
    }
