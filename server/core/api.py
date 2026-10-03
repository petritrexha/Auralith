"""Plugin API (`/api/v1/*`). Token auth via `Authorization: Bearer <token>`."""
from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.agent.analyzer import analyze
from core.models import Card, Profile, hash_token
from core.services import knowledge

log = logging.getLogger("core.api")
MAX_BODY_BYTES = 400_000
# Cards created while the plugin had already stopped waiting are re-sent on its next call, within this window.
REDELIVER_WINDOW_HOURS = 6
MAX_REDELIVER = 2


def _error(status: int, message: str) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def token_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return _error(401, "missing bearer token")
        raw = header[7:].strip()
        profile = (
            Profile.objects.select_related("user").filter(api_token_hash=hash_token(raw)).first() if raw else None
        )
        if profile is None or not profile.api_token_hash:
            return _error(401, "invalid token")
        if not profile.user.is_active:  # disabled users lose plugin access immediately
            return _error(403, "account disabled")
        request.user = profile.user
        request.profile = profile
        cache.set(f"ll:lastping:{profile.user.pk}", timezone.now(), 60 * 60 * 24 * 7)
        return view(request, *args, **kwargs)

    return wrapper


def rate_limited(view):
    """Fixed-window limit per token (per user), e.g. 30 requests / hour."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        limit = settings.LEARNLOOP["RATE_LIMIT_PER_HOUR"]
        window = int(time.time() // 3600)
        key = f"ll:rl:{request.user.pk}:{window}"
        cache.add(key, 0, 3700)
        count = cache.incr(key)
        if count > limit:
            return JsonResponse({"error": "rate limit exceeded", "cards": []}, status=429)
        return view(request, *args, **kwargs)

    return wrapper


@require_GET
@token_required
def ping(request):
    user = request.user
    return JsonResponse({"user": user.get_full_name() or user.email or user.username, "ok": True})


@csrf_exempt
@require_POST
@token_required
@rate_limited
def analyze_view(request):
    if len(request.body) > MAX_BODY_BYTES:
        return _error(413, "payload too large")
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _error(400, "invalid JSON")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        return _error(400, "'changes' must be a list")
    session_id = str(payload.get("session_id") or "")[:120]
    agent_message = str(payload.get("agent_message") or "")[:4000]
    _acknowledge(request.user, payload.get("ack"))
    missed = _undelivered(request.user)

    try:
        cards, log_row = analyze(request.user, session_id, changes, agent_message)
    except Exception:  # the plugin must never see a 500 it can't handle
        log.exception("analyze failed")
        return JsonResponse({"cards": [_card_json(c) for c in missed], "outcome": "error"})

    return JsonResponse({
        "cards": [_card_json(c) for c in [*missed, *cards]],
        "outcome": log_row.outcome,
        "mode": log_row.mode,
    })


def _acknowledge(user, ids) -> None:
    """The plugin sends back the ids of cards it displayed last time."""
    if not isinstance(ids, list):
        return
    clean = [int(i) for i in ids[:50] if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]
    if clean:
        Card.objects.filter(user=user, pk__in=clean, delivered_at__isnull=True).update(delivered_at=timezone.now())


def _undelivered(user) -> list[Card]:
    """Recent cards the terminal never showed (the plugin timed out while the agent was still working)."""
    since = timezone.now() - timedelta(hours=REDELIVER_WINDOW_HOURS)
    recent = (
        Card.objects.filter(user=user, delivered_at__isnull=True, created_at__gte=since)
        .select_related("concept").order_by("-created_at")[:10]
    )
    # Skip anything the user has since marked known or muted on the web.
    return [c for c in recent if not knowledge.is_blocked(user, c.concept.slug)][:MAX_REDELIVER]


def _card_json(c: Card) -> dict:
    return {
        "id": c.pk,
        "concept": c.concept.name,
        "category": c.concept.category,
        "summary": c.summary,
        "why_here": c.why_here,
        "file": c.file_path,
        "diagram": c.diagram_mermaid,
        "doc_url": c.doc_url,
        "url": c.public_url,
    }
