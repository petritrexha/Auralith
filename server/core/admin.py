from django.contrib import admin

from core.models import AnalyzeLog, Card, Concept, Profile, TeamReport, UserConcept


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "skill_level", "daily_card_limit", "token_prefix", "must_change_password", "last_active_at")
    readonly_fields = ("api_token_hash", "token_prefix")
    search_fields = ("user__email",)


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "created_at")
    list_filter = ("category",)
    search_fields = ("name", "slug")


@admin.register(UserConcept)
class UserConceptAdmin(admin.ModelAdmin):
    list_display = ("user", "concept", "status", "seen_count", "last_seen")
    list_filter = ("status", "concept__category")


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "concept", "file_path", "created_at", "read_at", "saved")
    list_filter = ("concept__category", "saved")
    search_fields = ("concept__name", "file_path", "user__email")


@admin.register(AnalyzeLog)
class AnalyzeLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "mode", "outcome", "files_count", "concepts_found", "cards_returned", "llm_calls", "duration_ms")
    list_filter = ("mode", "outcome")


@admin.register(TeamReport)
class TeamReportAdmin(admin.ModelAdmin):
    list_display = ("title", "created_at", "mode", "period_days")
