"""Integration checks for the server-rendered frontend and existing form contracts."""
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Card, Concept, TeamReport, UserConcept
from core.services.accounts import create_member


@override_settings(LEARNLOOP={**settings.LEARNLOOP, "MOCK_AI": True})
class FrontendIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member, _, _ = create_member(
            email="learner@example.com", password="Learn-Loop-123!", must_change_password=False
        )
        cls.admin, _, _ = create_member(
            email="admin@example.com", password="Admin-Loop-123!", is_admin=True,
            must_change_password=False,
        )
        cls.concept = Concept.objects.create(name="A & B <script>", slug="a-and-b", category="api")
        cls.card = Card.objects.create(
            user=cls.member, concept=cls.concept, summary="An explanation",
            why_here="A contextual explanation", code_snippet='<script>alert("unsafe")</script>',
            file_path="src/api.py", diagram_mermaid="graph LR; A-->B",
        )
        UserConcept.objects.create(user=cls.member, concept=cls.concept)

    def test_public_pages_and_empty_member_states(self):
        for route in ["landing", "login"]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        self.client.force_login(self.admin)
        for route in ["app-home", "cards", "concepts", "app-setup", "app-settings"]:
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "core/app.css")
        self.assertContains(self.client.get(reverse("cards")), "Your learning feed starts")

    def test_card_forms_preserve_every_action_and_escape_content(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("card-detail", args=[self.card.pk]))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("unsafe")</script>')
        for action, saved in [("save", True), ("unsave", False)]:
            response = self.client.post(reverse("card-action", args=[self.card.pk]), {"action": action}, follow=True)
            self.assertEqual(response.status_code, 200)
            self.card.refresh_from_db()
            self.assertEqual(self.card.saved, saved)
        for action, status in [("known", "known"), ("mute", "muted")]:
            self.client.post(reverse("card-action", args=[self.card.pk]), {"action": action})
            self.assertEqual(UserConcept.objects.get(user=self.member).status, status)
        self.client.post(reverse("concept-action", args=[self.concept.slug]), {"status": "seen"})
        self.assertEqual(UserConcept.objects.get(user=self.member).status, "seen")

    def test_search_pagination_preserves_special_characters(self):
        Card.objects.bulk_create([
            Card(user=self.member, concept=self.concept, summary="An explanation", why_here="Here")
            for _ in range(12)
        ])
        self.client.force_login(self.member)
        response = self.client.get(reverse("cards"), {"q": "A & B", "category": "api", "status": "unread"})
        self.assertContains(response, "q=A%20%26%20B")
        self.assertEqual(response.context["page"].paginator.count, 13)

    def test_settings_and_token_contracts(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("app-settings"), {
            "save_settings": "1", "s-skill_level": "intermediate", "s-daily_card_limit": "4",
        })
        self.assertEqual(response.status_code, 302)
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.daily_card_limit, 4)
        response = self.client.post(reverse("regenerate-token"), follow=True)
        self.assertContains(response, 'id="tok"')
        self.assertNotContains(self.client.get(reverse("app-setup")), 'id="tok"')

    @override_settings(DEBUG=False)
    def test_error_pages_keep_status_and_permissions(self):
        self.assertContains(self.client.get("/not-a-page/"), "outside the loop", status_code=404)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("manage-home")), "different key", status_code=403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("card-detail", args=[self.card.pk])).status_code, 404)

    def test_admin_forms_and_reports_are_available(self):
        self.client.force_login(self.admin)
        for route in ["manage-home", "manage-users", "manage-user-new", "manage-concepts", "manage-reports", "manage-activity"]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        response = self.client.get(reverse("manage-user", args=[self.member.pk]))
        for action in ["edit", "toggle_active", "reset_password", "regenerate_token"]:
            self.assertContains(response, f'value="{action}"')
        response = self.client.post(reverse("manage-reports"), {"days": "7"}, follow=True)
        self.assertEqual(response.status_code, 200)

    def test_mastery_history_uses_saved_snapshots_including_zero(self):
        TeamReport.objects.create(title="First snapshot", data={"org_mastery_rate": 0.0})
        TeamReport.objects.create(title="Next snapshot", data={"org_mastery_rate": 0.5})
        TeamReport.objects.create(title="Legacy report without snapshot")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage-home"))
        self.assertEqual(len(response.context["mastery_history"]), 2)
        self.assertContains(response, 'class="snapshot-value">0%</span>')
        self.assertContains(response, 'class="snapshot-value">50%</span>')
