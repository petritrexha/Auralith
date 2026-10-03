"""Run with:  python manage.py test core"""
import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.conf import settings

from core.agent import analyzer
from core.agent.reporter import generate_report
from core.models import AnalyzeLog, Card, UserConcept
from core.services import knowledge
from core.services.accounts import create_member
from core.services.scrub import is_secret_file, scrub_text

User = get_user_model()

REACT_DIFF = """+import { useReducer } from "react";
+function reducer(s, a) { return s; }
+export function Cart() {
+  const [items, dispatch] = useReducer(reducer, []);
+}"""

MOCK = {**settings.LEARNLOOP, "MOCK_AI": True}


@override_settings(LEARNLOOP=MOCK)
class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user, _, self.token = create_member(email="dev@example.com", full_name="Dev One", password="x-Secret-123", must_change_password=False)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def post(self, changes, **extra):
        return self.client.post("/api/v1/analyze", data=json.dumps({"session_id": "s", "changes": changes}), content_type="application/json", **{**self.auth, **extra})

    def test_ping(self):
        r = self.client.get("/api/v1/ping", **self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"], "Dev One")

    def test_bad_token(self):
        r = self.client.get("/api/v1/ping", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    def test_disabled_user_token_stops_working(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get("/api/v1/ping", **self.auth).status_code, 403)

    def test_analyze_creates_card(self):
        r = self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        cards = r.json()["cards"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["concept"], "React useReducer")
        self.assertIn("/app/cards/", cards[0]["url"])
        self.assertTrue(UserConcept.objects.filter(user=self.user, concept__slug="react-usereducer").exists())

    def test_known_concepts_are_not_repeated(self):
        self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        concept = Card.objects.get().concept
        knowledge.set_status(self.user, concept, UserConcept.Status.KNOWN)
        r = self.post([{"file": "web/Cart2.tsx", "diff": REACT_DIFF}])
        self.assertEqual(r.json()["cards"], [])

    def test_trivial_change_skipped(self):
        r = self.post([{"file": "a.py", "diff": "+x = 1"}])
        self.assertEqual(r.json()["outcome"], "trivial")

    def test_daily_limit(self):
        type(self.user.profile).objects.filter(user=self.user).update(daily_card_limit=0)
        r = self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        self.assertEqual(r.json().get("cards"), [], r.content)
        self.assertEqual(AnalyzeLog.objects.get().outcome, "daily_limit")

    def test_secret_files_never_analyzed(self):
        self.post([{"file": ".env.production", "diff": REACT_DIFF * 3}])
        self.assertEqual(Card.objects.count(), 0)

    @override_settings(LEARNLOOP={**MOCK, "RATE_LIMIT_PER_HOUR": 2})
    def test_rate_limit(self):
        for _ in range(2):
            self.post([{"file": "a.py", "diff": "+x"}])
        self.assertEqual(self.post([{"file": "a.py", "diff": "+x"}]).status_code, 429)


class ScrubTests(TestCase):
    def test_patterns(self):
        text = 'api_key = "abcdef123456"\nkey=sk-ant-api03-aaaaaaaaaaaaaaaa\npostgres://u:p@h/db'
        out = scrub_text(text)
        self.assertNotIn("abcdef123456", out)
        self.assertNotIn("sk-ant-api03", out)
        self.assertNotIn("u:p@h", out)
        self.assertTrue(is_secret_file("C:\\proj\\.env"))
        self.assertTrue(is_secret_file("certs/server.pem"))
        self.assertFalse(is_secret_file("src/env.ts"))


@override_settings(LEARNLOOP=MOCK)
class WebTests(TestCase):
    def setUp(self):
        self.a, _, _ = create_member(email="a@example.com", password="pw-Alpha-123", must_change_password=False)
        self.b, _, _ = create_member(email="b@example.com", password="pw-Beta-123", must_change_password=False)
        cards, _ = analyzer.analyze(self.a, "s", [{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        self.card = cards[0]

    def test_member_cannot_read_others_cards(self):
        self.client.login(username="b@example.com", password="pw-Beta-123")
        self.assertEqual(self.client.get(f"/app/cards/{self.card.pk}").status_code, 404)

    def test_owner_reads_and_marks_known(self):
        self.client.login(username="a@example.com", password="pw-Alpha-123")
        self.assertEqual(self.client.get(f"/app/cards/{self.card.pk}").status_code, 200)
        self.client.post(f"/app/cards/{self.card.pk}/action", {"action": "known"})
        self.assertEqual(UserConcept.objects.get(user=self.a).status, "known")

    def test_members_blocked_from_manage(self):
        self.client.login(username="a@example.com", password="pw-Alpha-123")
        self.assertEqual(self.client.get("/manage/").status_code, 403)

    def test_first_login_forces_password_change(self):
        create_member(email="new@example.com", password="tmp-Pass-123")
        self.client.login(username="new@example.com", password="tmp-Pass-123")
        r = self.client.get("/app/")
        self.assertRedirects(r, "/app/first-login/")

    def test_admin_pages_render(self):
        create_member(email="boss@example.com", password="pw-Boss-123", is_admin=True, must_change_password=False)
        self.client.login(username="boss@example.com", password="pw-Boss-123")
        for url in ["/manage/", "/manage/users/", "/manage/concepts/", "/manage/reports/", "/manage/activity/", f"/manage/users/{self.a.pk}/", "/manage/insights.json"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post("/manage/reports/", {"days": 7})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(r["Location"]).status_code, 200)

    def test_member_pages_render(self):
        self.client.login(username="a@example.com", password="pw-Alpha-123")
        for url in ["/app/", "/app/cards/", "/app/concepts/", "/app/setup/", "/app/settings/", "/app/insights.json", "/app/setup/status"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)


def _block(**kw):
    return SimpleNamespace(**kw)


class FakeAnthropic:
    """Scripted model: turn 1 checks knowledge + docs, turn 2 creates a card and skips one."""

    def __init__(self):
        self.turn = 0
        self.messages = self

    def create(self, **kwargs):
        self.turn += 1
        usage = SimpleNamespace(input_tokens=900, output_tokens=150)
        if self.turn == 1:
            content = [
                _block(type="text", text="Candidates: react-usereducer, javascript-functions."),
                _block(type="tool_use", id="t1", name="check_user_knowledge", input={"slugs": ["react-usereducer", "javascript-functions"]}),
                _block(type="tool_use", id="t2", name="find_docs", input={"query": "react useReducer"}),
            ]
            return SimpleNamespace(content=content, stop_reason="tool_use", usage=usage)
        if self.turn == 2:
            content = [
                _block(type="tool_use", id="t3", name="skip_concept", input={"slug": "javascript-functions", "reason": "too basic"}),
                _block(type="tool_use", id="t4", name="create_card", input={
                    "concept_name": "React useReducer", "slug": "react-usereducer", "category": "frontend",
                    "summary": "useReducer centralises state updates.", "why_here": "Cart.tsx keeps cart items in a reducer.",
                    "file_path": "web/Cart.tsx", "doc_url": "https://react.dev/reference/react/useReducer",
                }),
            ]
            return SimpleNamespace(content=content, stop_reason="tool_use", usage=usage)
        return SimpleNamespace(content=[_block(type="text", text="Done.")], stop_reason="end_turn", usage=usage)


@override_settings(LEARNLOOP={**settings.LEARNLOOP, "MOCK_AI": False, "ANTHROPIC_API_KEY": "test-key", "VERIFY_LINKS": False})
class LiveAgentLoopTests(TestCase):
    def test_tool_loop_creates_card_and_traces(self):
        user, _, _ = create_member(email="live@example.com", password="pw-Live-123")
        fake = FakeAnthropic()
        with mock.patch("core.agent.llm._client", return_value=fake):
            cards, log = analyzer.analyze(user, "s", [{"file": "web/Cart.tsx", "diff": REACT_DIFF}], "Added a cart reducer")
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0].doc_verified)
        self.assertEqual(log.mode, "live")
        self.assertEqual(log.llm_calls, 3)
        self.assertEqual(log.input_tokens, 2700)
        tools = [s.get("tool") for s in log.trace if s["type"] == "tool"]
        self.assertEqual(tools, ["check_user_knowledge", "find_docs", "skip_concept", "create_card"])

    def test_llm_failure_is_graceful(self):
        user, _, _ = create_member(email="live2@example.com", password="pw-Live-123")
        broken = SimpleNamespace(messages=SimpleNamespace(create=mock.Mock(side_effect=RuntimeError("overloaded"))))
        with mock.patch("core.agent.llm._client", return_value=broken):
            cards, log = analyzer.analyze(user, "s", [{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        self.assertEqual(cards, [])
        self.assertEqual(log.outcome, "error")


@override_settings(LEARNLOOP=MOCK)
class ReporterTests(TestCase):
    def test_mock_report(self):
        u, _, _ = create_member(email="r@example.com", password="pw-R-12345")
        analyzer.analyze(u, "s", [{"file": "web/src/Cart.tsx", "diff": REACT_DIFF}])
        report = generate_report(days=7)
        self.assertIn("Risk hotspots", report.body_markdown)
        self.assertIn("web/src", report.body_markdown)
