"""Everything about a user's knowledge profile: concepts, statuses, exposure."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from core.models import Concept, Profile, UserConcept
from core.services import checklist

User = get_user_model()

# Common aliases so "jwt-refresh-token-rotation" and "jwt-refresh-rotation" land on one concept.
SLUG_ALIASES = {
    "jwt-refresh-token-rotation": "jwt-refresh-rotation",
    "refresh-token-rotation": "jwt-refresh-rotation",
    "react-usereducer-hook": "react-usereducer",
    "usereducer": "react-usereducer",
    "useeffect-cleanup": "react-useeffect-cleanup",
    "css-flexbox-centering": "flexbox-centering",
    "center-div-flexbox": "flexbox-centering",
    "entity-framework-migrations": "ef-core-migrations",
    "ef-migrations": "ef-core-migrations",
}

VALID_CATEGORIES = {c.value for c in Concept.Category}


def normalize_slug(name_or_slug: str) -> str:
    slug = slugify(name_or_slug)[:120].strip("-")
    return SLUG_ALIASES.get(slug, slug)


def get_profile(user) -> Profile:
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


def get_or_create_concept(name: str, slug: str | None = None, category: str = "other") -> Concept:
    slug = normalize_slug(slug or name)
    category = category if category in VALID_CATEGORIES else "other"
    concept, created = Concept.objects.get_or_create(slug=slug, defaults={"name": name[:120], "category": category})
    if not created and concept.category == "other" and category != "other":
        concept.category = category
        concept.save(update_fields=["category"])
    return concept


BLOCKING = [UserConcept.Status.KNOWN, UserConcept.Status.MUTED]


def known_topic_slugs(user) -> list[str]:
    """Checklist topics the user ticked as known."""
    return list(
        UserConcept.objects.filter(user=user, status=UserConcept.Status.KNOWN, concept__slug__in=list(checklist.TOPICS))
        .values_list("concept__slug", flat=True)
    )


def statuses_for(user, slugs: list[str]) -> dict[str, dict]:
    """Return {slug: {"status", "seen_count"}} for the requested slugs (missing = never seen).

    A concept covered by a ticked checklist topic reports "known" with `covered_by`.
    """
    normalized = {normalize_slug(s): s for s in slugs}
    rows = UserConcept.objects.filter(user=user, concept__slug__in=list(normalized)).select_related("concept")
    found = {uc.concept.slug: {"status": uc.status, "seen_count": uc.seen_count} for uc in rows}
    topics = known_topic_slugs(user)
    result = {}
    for slug in normalized:
        entry = found.get(slug, {"status": "never_seen", "seen_count": 0})
        covering = checklist.covering_topics(slug, topics)
        if covering and entry["status"] not in BLOCKING:
            entry = {**entry, "status": "known", "covered_by": covering[0].name}
        result[slug] = entry
    return result


def is_blocked(user, slug: str) -> bool:
    """Known or muted concepts, and anything inside a ticked checklist topic, must never produce a card."""
    slug = normalize_slug(slug)
    if UserConcept.objects.filter(user=user, concept__slug=slug, status__in=BLOCKING).exists():
        return True
    return bool(checklist.covering_topics(slug, known_topic_slugs(user)))


def set_topic_known(user, topic_slug: str, known: bool) -> None:
    """Tick / untick a checklist topic. Unticking a topic that never came up in real work removes it entirely."""
    topic = checklist.TOPICS[topic_slug]
    concept = get_or_create_concept(topic.name, topic.slug, checklist.SECTOR_OF[topic_slug].category)
    if known:
        set_status(user, concept, UserConcept.Status.KNOWN)
        return
    uc = UserConcept.objects.filter(user=user, concept=concept).first()
    if uc is None:
        return
    if uc.seen_count == 0:
        uc.delete()
    else:
        set_status(user, concept, UserConcept.Status.SEEN)


@transaction.atomic
def record_exposure(user, concept: Concept) -> UserConcept:
    now = timezone.now()
    uc, created = UserConcept.objects.select_for_update().get_or_create(
        user=user, concept=concept, defaults={"status": UserConcept.Status.NEW, "seen_count": 1, "first_seen": now, "last_seen": now}
    )
    if not created:
        uc.seen_count += 1
        uc.last_seen = now
        if uc.status == UserConcept.Status.NEW:
            uc.status = UserConcept.Status.SEEN
        uc.save(update_fields=["seen_count", "last_seen", "status"])
    return uc


def set_status(user, concept: Concept, status: str) -> UserConcept:
    if status not in {s.value for s in UserConcept.Status}:
        raise ValueError(f"invalid status {status}")
    uc, _ = UserConcept.objects.get_or_create(user=user, concept=concept)
    uc.status = status
    uc.known_at = timezone.now() if status == UserConcept.Status.KNOWN else None
    if status != UserConcept.Status.KNOWN:
        uc.verified_at = None
    uc.save(update_fields=["status", "known_at", "verified_at"])
    return uc


def known_slugs(user, limit: int = 200) -> list[str]:
    """Concepts the user already knows or muted — given to the agent so it doesn't waste a turn on them."""
    return list(
        UserConcept.objects.filter(user=user, status__in=BLOCKING)
        .exclude(concept__slug__in=list(checklist.TOPICS))
        .order_by("-last_seen")
        .values_list("concept__slug", flat=True)[:limit]
    )


def known_topic_names(user) -> list[str]:
    return [checklist.TOPICS[s].name for s in known_topic_slugs(user)]
