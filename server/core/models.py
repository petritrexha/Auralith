import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

TOKEN_PREFIX = "ll_"
# Concepts created by ticking the skill checklist (core/services/checklist.py).
CHECKLIST_SLUG_PREFIX = "stack-"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Profile(models.Model):
    class Skill(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"

    class Depth(models.TextChoices):
        BRIEF = "brief", "Brief"
        STANDARD = "standard", "Standard"
        DEEP = "deep", "Deep dive"

    class TerminalDetail(models.TextChoices):
        COMPACT = "compact", "Compact"
        VISUAL = "visual", "With flow + pitfall"
        LINK = "link", "Just a link"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    api_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    token_prefix = models.CharField(max_length=16, blank=True, help_text="First characters of the token, for display only")
    skill_level = models.CharField(max_length=20, choices=Skill.choices, default=Skill.BEGINNER)
    daily_card_limit = models.PositiveIntegerField(default=8)
    must_change_password = models.BooleanField(default=True)
    # How cards are written for this person (Settings → "Personalize your cards").
    explanation_depth = models.CharField(max_length=10, choices=Depth.choices, default=Depth.STANDARD)
    show_diagrams = models.BooleanField(default=True, help_text="Add a small diagram when a concept has a flow or relationship")
    use_analogies = models.BooleanField(default=True, help_text="Add a one-line everyday comparison")
    terminal_detail = models.CharField(max_length=10, choices=TerminalDetail.choices, default=TerminalDetail.COMPACT)
    last_active_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile({self.user.email or self.user.username})"

    def regenerate_token(self) -> str:
        """Create a new token, store only its hash, and return the raw value ONCE."""
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        self.api_token_hash = hash_token(raw)
        self.token_prefix = raw[:10]
        self.save(update_fields=["api_token_hash", "token_prefix"])
        return raw

    def cards_today(self) -> int:
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.user.cards.filter(created_at__gte=start).count()


class Concept(models.Model):
    class Category(models.TextChoices):
        AUTH = "auth", "Auth"
        DATABASE = "database", "Database"
        FRONTEND = "frontend", "Frontend"
        API = "api", "API"
        DEVOPS = "devops", "DevOps"
        TESTING = "testing", "Testing"
        SECURITY = "security", "Security"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserConceptQuerySet(models.QuerySet):
    def from_work(self):
        """Drop checklist ticks that never came up in real work: they're self-reported, not surfaced by the agent."""
        return self.exclude(concept__slug__startswith=CHECKLIST_SLUG_PREFIX, seen_count=0)


class UserConcept(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        SEEN = "seen", "Seen"
        KNOWN = "known", "Known"
        MUTED = "muted", "Muted"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_concepts")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="user_concepts")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    seen_count = models.PositiveIntegerField(default=0)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    known_at = models.DateTimeField(null=True, blank=True)
    # Set when the user passed an "explain it in your own words" check with clean integrity signals.
    verified_at = models.DateTimeField(null=True, blank=True)

    objects = UserConceptQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "concept"], name="unique_user_concept")]

    def __str__(self):
        return f"{self.user} · {self.concept} · {self.status}"

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class Card(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cards")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="cards")
    summary = models.TextField()
    why_here = models.TextField()
    diagram_mermaid = models.TextField(blank=True)
    pitfall = models.TextField(blank=True)
    analogy = models.TextField(blank=True)
    doc_url = models.URLField(max_length=500, blank=True)
    doc_verified = models.BooleanField(default=False)
    code_snippet = models.TextField(blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    session_id = models.CharField(max_length=120, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    saved = models.BooleanField(default=False)
    # Set when the plugin confirms it showed the card in the terminal (see api.analyze_view).
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Card#{self.pk} {self.concept} for {self.user}"

    @property
    def public_url(self) -> str:
        return f"{settings.LEARNLOOP['PUBLIC_URL']}/app/cards/{self.pk}"


class AnalyzeLog(models.Model):
    """One row per /analyze call. `trace` records the agent's decisions (great for demos and debugging)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analyze_logs")
    created_at = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=120, blank=True)
    files_count = models.PositiveIntegerField(default=0)
    concepts_found = models.PositiveIntegerField(default=0)
    cards_returned = models.PositiveIntegerField(default=0)
    llm_calls = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    mode = models.CharField(max_length=10, default="live")  # live | mock | skipped
    outcome = models.CharField(max_length=40, default="ok")  # ok | daily_limit | trivial | error | budget
    trace = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ComprehensionCheck(models.Model):
    """'Explain it in your own words' check for one card, graded by the agent, with anti-AI integrity signals."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PASSED = "passed", "Passed"
        PARTIAL = "partial", "Almost"
        FAILED = "failed", "Not yet"
        UNVERIFIED = "unverified", "Couldn't verify"  # good answer, but integrity signals too strong
        EXPIRED = "expired", "Time ran out"

    class Integrity(models.TextChoices):
        CLEAN = "clean", "Clean"
        REVIEW = "review", "Review"
        FLAGGED = "flagged", "Flagged"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checks")
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="checks")
    question = models.TextField()
    key_points = models.JSONField(default=list, blank=True)
    time_limit_seconds = models.PositiveIntegerField(default=240)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    score = models.PositiveIntegerField(null=True, blank=True)  # 0-100
    rubric = models.JSONField(default=dict, blank=True)  # correctness / application / reasoning
    feedback = models.TextField(blank=True)
    missed_points = models.JSONField(default=list, blank=True)
    integrity = models.CharField(max_length=10, choices=Integrity.choices, default=Integrity.CLEAN)
    suspicion = models.PositiveIntegerField(default=0)  # 0-100
    integrity_signals = models.JSONField(default=list, blank=True)  # human-readable reasons
    telemetry = models.JSONField(default=dict, blank=True)  # raw client signals
    mode = models.CharField(max_length=10, default="live")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Check#{self.pk} {self.card.concept} · {self.status}"

    @property
    def deadline(self):
        return self.started_at + timedelta(seconds=self.time_limit_seconds)


class TeamReport(models.Model):
    """Weekly manager briefing written by the reporting agent."""

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    period_days = models.PositiveIntegerField(default=7)
    title = models.CharField(max_length=200)
    body_markdown = models.TextField()
    data = models.JSONField(default=dict, blank=True)  # the raw numbers the agent looked at
    mode = models.CharField(max_length=10, default="live")
    trace = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
