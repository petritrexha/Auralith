import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

TOKEN_PREFIX = "ll_"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Profile(models.Model):
    class Skill(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    api_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    token_prefix = models.CharField(max_length=16, blank=True, help_text="First characters of the token, for display only")
    skill_level = models.CharField(max_length=20, choices=Skill.choices, default=Skill.BEGINNER)
    daily_card_limit = models.PositiveIntegerField(default=8)
    must_change_password = models.BooleanField(default=True)
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

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "concept"], name="unique_user_concept")]

    def __str__(self):
        return f"{self.user} · {self.concept} · {self.status}"


class Card(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cards")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="cards")
    summary = models.TextField()
    why_here = models.TextField()
    diagram_mermaid = models.TextField(blank=True)
    doc_url = models.URLField(max_length=500, blank=True)
    doc_verified = models.BooleanField(default=False)
    code_snippet = models.TextField(blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    session_id = models.CharField(max_length=120, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    saved = models.BooleanField(default=False)

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
