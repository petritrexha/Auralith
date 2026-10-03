from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core import api, views
from core.forms import EmailLoginForm

urlpatterns = [
    # Public
    path("", views.landing, name="landing"),
    path("login/", auth_views.LoginView.as_view(authentication_form=EmailLoginForm, redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("healthz", views.healthz, name="healthz"),
    # Member
    path("app/", views.app_home, name="app-home"),
    path("app/insights.json", views.member_insights_json, name="app-insights-json"),
    path("app/cards/", views.card_list, name="cards"),
    path("app/cards/latest.json", views.cards_latest_json, name="cards-latest-json"),
    path("app/cards/<int:pk>", views.card_detail, name="card-detail"),
    path("app/cards/<int:pk>/action", views.card_action, name="card-action"),
    path("app/cards/<int:pk>/check", views.check_start, name="check-start"),
    path("app/checks/<int:pk>", views.check_page, name="check"),
    path("app/checks/<int:pk>/submit", views.check_submit, name="check-submit"),
    path("app/checks/<int:pk>/result", views.check_result, name="check-result"),
    path("app/concepts/", views.concepts, name="concepts"),
    path("app/concepts/checklist", views.concept_checklist, name="concept-checklist"),
    path("app/concepts/<slug:slug>/status", views.concept_action, name="concept-action"),
    path("app/setup/", views.setup, name="app-setup"),
    path("app/setup/status", views.setup_status, name="app-setup-status"),
    path("app/setup/regenerate", views.regenerate_token, name="regenerate-token"),
    path("app/settings/", views.user_settings, name="app-settings"),
    path("app/personalize/", views.personalize, name="personalize"),
    path("app/first-login/", views.first_login, name="first-login"),
    # Admin
    path("manage/", views.manage_home, name="manage-home"),
    path("manage/insights.json", views.org_insights_json, name="manage-insights-json"),
    path("manage/users/", views.manage_users, name="manage-users"),
    path("manage/users/new/", views.manage_user_new, name="manage-user-new"),
    path("manage/users/<int:pk>/", views.manage_user_detail, name="manage-user"),
    path("manage/concepts/", views.manage_concepts, name="manage-concepts"),
    path("manage/reports/", views.manage_reports, name="manage-reports"),
    path("manage/reports/<int:pk>/", views.manage_report, name="manage-report"),
    path("manage/activity/", views.manage_activity, name="manage-activity"),
    path("manage/checks/", views.manage_checks, name="manage-checks"),
    path("manage/checks/<int:pk>/review", views.manage_check_review, name="manage-check-review"),
    path("django-admin/", admin.site.urls),
    # Plugin API
    path("api/v1/ping", api.ping, name="api-ping"),
    path("api/v1/analyze", api.analyze_view, name="api-analyze"),
    path("api/v1/cards", api.cards_view, name="api-cards"),
    path("api/v1/cards/<int:pk>/action", api.card_action_view, name="api-card-action"),
]
