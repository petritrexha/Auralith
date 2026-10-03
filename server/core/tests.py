"""Run with:  python manage.py test core"""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django.conf import settings

from core.agent import analyzer
from core.agent.reporter import generate_report
from core.models import AnalyzeLog, Card, UserConcept
from core.services import checklist, knowledge
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

    def test_checklist_topic_blocks_narrower_concepts(self):
        knowledge.set_topic_known(self.user, "stack-react-hooks", True)
        r = self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        self.assertEqual(r.json()["cards"], [])
        skips = [s["input"]["reason"] for s in AnalyzeLog.objects.get().trace if s.get("tool") == "skip_concept"]
        self.assertTrue(any("checklist" in reason for reason in skips), skips)
        self.assertTrue(knowledge.is_blocked(self.user, "usereducer-for-complex-state"))
        self.assertFalse(knowledge.is_blocked(self.user, "css-grid"))

    def test_undelivered_cards_are_resent_until_acked(self):
        card_id = self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}]).json()["cards"][0]["id"]
        # Plugin timed out and never acked: the next call (even a trivial one) carries the card again.
        r = self.post([{"file": "a.py", "diff": "+x = 1"}])
        self.assertEqual([c["id"] for c in r.json()["cards"]], [card_id])
        body = {"session_id": "s", "changes": [{"file": "a.py", "diff": "+x = 1"}], "ack": [card_id]}
        r = self.client.post("/api/v1/analyze", data=json.dumps(body), content_type="application/json", **self.auth)
        self.assertEqual(r.json()["cards"], [])
        self.assertIsNotNone(Card.objects.get(pk=card_id).delivered_at)

    def test_niche_tick_only_blocks_that_skill(self):
        knowledge.set_topic_known(self.user, "stack-react-hooks-usereducer", True)
        self.assertTrue(knowledge.is_blocked(self.user, "react-usereducer"))
        self.assertFalse(knowledge.is_blocked(self.user, "react-useeffect-cleanup"))
        self.assertEqual(checklist.progress(knowledge.known_topic_slugs(self.user))["count"], 1)
        knowledge.set_topic_known(self.user, "stack-react-hooks", True)  # whole topic = all its skills
        self.assertEqual(checklist.progress(knowledge.known_topic_slugs(self.user))["count"], 7)

    def test_editor_cards_api(self):
        card_id = self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}]).json()["cards"][0]["id"]
        data = self.client.get("/api/v1/cards", **self.auth).json()
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["cards"][0]["id"], card_id)
        self.assertFalse(data["cards"][0]["read"])
        act = lambda a: self.client.post(f"/api/v1/cards/{card_id}/action", data=json.dumps({"action": a}), content_type="application/json", **self.auth)
        self.assertEqual(act("read").status_code, 200)
        self.assertEqual(act("known").status_code, 200)
        self.assertEqual(act("explode").status_code, 400)
        data = self.client.get("/api/v1/cards", **self.auth).json()
        self.assertEqual((data["unread"], data["cards"][0]["status"]), (0, "known"))
        self.assertEqual(self.client.get("/api/v1/cards").status_code, 401)
        other, _, other_token = create_member(email="other@example.com", password="pw-Other-123")
        r = self.client.post(f"/api/v1/cards/{card_id}/action", data=json.dumps({"action": "read"}), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {other_token}")
        self.assertEqual(r.status_code, 404)

    def test_card_preferences_shape_new_cards(self):
        card = self.post([{"file": "web/Cart.tsx", "diff": REACT_DIFF}]).json()["cards"][0]
        self.assertTrue(card["diagram"] and card["flow"] and card["pitfall"] and card["analogy"])
        self.assertEqual(self.client.post("/api/v1/analyze", data=json.dumps({"changes": [{"file": "a.py", "diff": "+x = 1"}], "ack": [card["id"]]}),
                                          content_type="application/json", **self.auth).json()["terminal"], "compact")
        profile = knowledge.get_profile(self.user)
        profile.explanation_depth, profile.show_diagrams, profile.use_analogies = "brief", False, False
        profile.save()
        Card.objects.all().delete()
        UserConcept.objects.all().delete()
        card = self.post([{"file": "web/Cart2.tsx", "diff": REACT_DIFF}]).json()["cards"][0]
        self.assertEqual((card["diagram"], card["flow"], card["pitfall"], card["analogy"]), ("", [], "", ""))
        from core.agent.catalog import BY_SLUG
        self.assertLess(len(card["summary"]), len(BY_SLUG["react-usereducer"].summary))  # brief = first sentence only
        self.assertEqual(card["summary"].count(". "), 0)
        stored = Card.objects.get(pk=card["id"])
        self.assertEqual((stored.diagram_mermaid, stored.pitfall, stored.analogy), ("", "", ""))

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

    def test_checklist_toggle(self):
        self.client.login(username="a@example.com", password="pw-Alpha-123")
        r = self.client.post("/app/concepts/checklist", {"topic": "stack-docker", "known": "1"})
        self.assertEqual(r.json()["known"], True)
        self.assertEqual(knowledge.known_topic_slugs(self.a), ["stack-docker"])
        self.assertContains(self.client.get("/app/concepts/"), 'value="stack-docker" data-general checked')
        self.assertContains(self.client.get("/app/concepts/"), "starting map, not every skill")
        self.client.post("/app/concepts/checklist", {"topic": "stack-docker", "known": "0"})
        self.assertFalse(UserConcept.objects.filter(user=self.a, concept__slug="stack-docker").exists())
        # No-JS fallback saves the whole form.
        self.client.post("/app/concepts/checklist", {"topics": ["stack-jwt", "stack-sql"]})
        self.assertEqual(sorted(knowledge.known_topic_slugs(self.a)), ["stack-jwt", "stack-sql"])
        self.assertEqual(self.client.post("/app/concepts/checklist", {"topic": "nope"}).status_code, 400)
        # Self-reported ticks never inflate the "concepts surfaced" stats managers see.
        surfaced = self.client.get("/app/insights.json").json()["surfaced"]
        self.assertEqual(surfaced, 1)
        self.assertContains(self.client.get("/app/"), "Your skill map")
        self.assertEqual(self.client.get("/app/cards/latest.json").json()["latest_id"], self.card.pk)

    def test_personalize_page(self):
        self.client.login(username="a@example.com", password="pw-Alpha-123")
        r = self.client.get("/app/personalize/")
        self.assertContains(r, "Personalize your cards")
        self.assertContains(r, "data-diagram")
        self.client.post("/app/personalize/", {"explanation_depth": "deep", "terminal_detail": "visual", "show_diagrams": "on"})
        profile = knowledge.get_profile(self.a)
        self.assertEqual((profile.explanation_depth, profile.terminal_detail, profile.show_diagrams, profile.use_analogies),
                         ("deep", "visual", True, False))
        # Diagram shows on the card page only while diagrams are on.
        self.assertContains(self.client.get(f"/app/cards/{self.card.pk}"), "AT A GLANCE")
        profile.show_diagrams = False
        profile.save()
        self.assertNotContains(self.client.get(f"/app/cards/{self.card.pk}"), "AT A GLANCE")

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


class ChecklistCoverageTests(TestCase):
    def test_patterns(self):
        hooks = checklist.TOPICS["stack-react-hooks"]
        for slug in ["react-usereducer", "react-useeffect-cleanup", "usestate-hook", "custom-hooks"]:
            self.assertTrue(hooks.covers(slug), slug)
        for slug in ["css-grid", "user-profile", "reuse-components"]:
            self.assertFalse(hooks.covers(slug), slug)
        self.assertTrue(checklist.TOPICS["stack-web-security"].covers("cors"))
        self.assertFalse(checklist.TOPICS["stack-web-security"].covers("decorators"))
        self.assertTrue(checklist.TOPICS["stack-db-performance"].covers("n-plus-one-queries"))


class VisualsTests(TestCase):
    def test_clean_mermaid(self):
        from core.services.visuals import clean_mermaid, flow_lines
        self.assertEqual(clean_mermaid("```mermaid\ngraph LR\n  A-->B\n```"), "graph LR\n  A-->B")
        self.assertEqual(clean_mermaid("graph LR\n  A-->B\n  click A \"javascript:alert(1)\""), "")
        self.assertEqual(clean_mermaid("not a diagram"), "")
        self.assertEqual(flow_lines("graph LR\n  Q[Request] --> M[Logger] --> H[Handler]"), ["Request → Logger → Handler"])
        self.assertEqual(flow_lines("sequenceDiagram\n  participant B as Browser\n  B->>S: GET /"), ["Browser → S: GET /"])

    def test_terminal_formats(self):
        import sys
        sys.path.insert(0, str(settings.BASE_DIR.parent / "plugin" / "scripts"))
        from flush import format_card
        card = {"concept": "CORS", "summary": "Browsers block cross-origin calls.", "why_here": "api.ts calls another origin.",
                "flow": ["Browser → API: OPTIONS preflight"], "pitfall": "Wildcard origins break cookies.", "url": "http://x/app/cards/1"}
        self.assertNotIn("Watch out", format_card(card, "compact"))
        self.assertIn("▸ Browser → API: OPTIONS preflight", format_card(card, "visual"))
        self.assertIn("Watch out", format_card(card, "visual"))
        self.assertNotIn("Browsers block", format_card(card, "link"))


# ---------------------------------------------------------------------------
# Comprehension checks + anti-AI integrity
# ---------------------------------------------------------------------------
from core.agent import checker  # noqa: E402
from core.models import ComprehensionCheck  # noqa: E402
from core.services import integrity  # noqa: E402

HUMAN_ANSWER = ("useReducer keeps the cart state in one reducer function in Cart.tsx, so every change is an action "
                "like add or remove. if i removed it i would need lots of useState calls and the cart state could get "
                "out of sync because updates would be spread around")
HUMAN_TELEMETRY = {"keystrokes": 260, "typed_chars": 255, "paste_attempts": 0, "blur_count": 0,
                   "hidden_seconds": 0, "active_typing_seconds": 70}


@override_settings(LEARNLOOP=MOCK)
class CheckFlowTests(TestCase):
    def setUp(self):
        self.user, _, _ = create_member(email="c@example.com", password="pw-Check-123", must_change_password=False)
        cards, _ = analyzer.analyze(self.user, "s", [{"file": "web/Cart.tsx", "diff": REACT_DIFF}])
        self.card = cards[0]

    def _submit(self, answer, telemetry, seconds_ago=90):
        check = checker.start_check(self.user, self.card)
        ComprehensionCheck.objects.filter(pk=check.pk).update(started_at=timezone.now() - timedelta(seconds=seconds_ago))
        check.refresh_from_db()
        return checker.submit_check(check, answer, telemetry)

    def test_question_mentions_their_file(self):
        check = checker.start_check(self.user, self.card)
        self.assertIn("Cart.tsx", check.question)
        self.assertTrue(check.key_points)

    def test_good_typed_answer_is_verified(self):
        check = self._submit(HUMAN_ANSWER, HUMAN_TELEMETRY)
        self.assertEqual(check.integrity, "clean", check.integrity_signals)
        self.assertEqual(check.status, "passed", (check.score, check.rubric))
        uc = UserConcept.objects.get(user=self.user, concept=self.card.concept)
        self.assertTrue(uc.is_verified)

    def test_injected_text_is_not_verified(self):
        tele = {**HUMAN_TELEMETRY, "typed_chars": 12, "keystrokes": 12, "paste_attempts": 2}
        check = self._submit(HUMAN_ANSWER, tele)
        self.assertEqual(check.integrity, "flagged")
        self.assertIn(check.status, ("unverified", "partial", "failed"))
        uc = UserConcept.objects.filter(user=self.user, concept=self.card.concept).first()
        self.assertFalse(uc and uc.is_verified)

    def test_missing_telemetry_is_suspicious(self):
        check = self._submit(HUMAN_ANSWER, {})
        self.assertNotEqual(check.integrity, "clean")

    def test_expired(self):
        check = self._submit(HUMAN_ANSWER, HUMAN_TELEMETRY, seconds_ago=1000)
        self.assertEqual(check.status, "expired")

    def test_attempt_limit(self):
        for _ in range(checker.MAX_ATTEMPTS_PER_DAY):
            checker.start_check(self.user, self.card)
        with self.assertRaises(checker.CheckError):
            checker.start_check(self.user, self.card)

    def test_cannot_open_others_check(self):
        other, _, _ = create_member(email="o@example.com", password="pw-Other-123", must_change_password=False)
        check = checker.start_check(self.user, self.card)
        self.client.login(username="o@example.com", password="pw-Other-123")
        self.assertEqual(self.client.get(f"/app/checks/{check.pk}").status_code, 404)

    def test_web_flow_and_admin_review(self):
        self.client.login(username="c@example.com", password="pw-Check-123")
        r = self.client.post(f"/app/cards/{self.card.pk}/check")
        check = ComprehensionCheck.objects.get()
        self.assertRedirects(r, f"/app/checks/{check.pk}")
        self.assertContains(self.client.get(r["Location"]), "Explain it in your own words")
        ComprehensionCheck.objects.filter(pk=check.pk).update(started_at=timezone.now() - timedelta(seconds=80))
        r = self.client.post(f"/app/checks/{check.pk}/submit", {"answer": HUMAN_ANSWER, "telemetry": json.dumps({**HUMAN_TELEMETRY, "hidden_seconds": 90})})
        self.assertEqual(self.client.get(r["Location"]).status_code, 200)
        check.refresh_from_db()
        self.assertEqual(check.integrity, "review")
        create_member(email="boss2@example.com", password="pw-Boss-123", is_admin=True, must_change_password=False)
        self.client.login(username="boss2@example.com", password="pw-Boss-123")
        self.assertEqual(self.client.get("/manage/checks/?only=attention").status_code, 200)
        self.client.post(f"/manage/checks/{check.pk}/review", {"decision": "accept"})
        self.assertTrue(UserConcept.objects.get(user=self.user, concept=self.card.concept).is_verified)


class IntegrityTests(TestCase):
    def test_copying_the_card_is_detected(self):
        card_text = "useReducer manages state through a reducer function state action newState instead of many useState calls"
        answer = "useReducer manages state through a reducer function state action newState instead of many useState calls yes"
        r = integrity.assess(answer, {**HUMAN_TELEMETRY, "typed_chars": len(answer)}, card_text, 90)
        self.assertTrue(any("repeats the card" in s for s in r.signals))

    def test_ai_style_markers(self):
        text = "Furthermore, it's important to note that this ensures that state is robust. In summary, it plays a crucial role."
        self.assertGreaterEqual(len(integrity.style_markers(text)), 2)

    def test_superhuman_typing(self):
        r = integrity.assess("x" * 400, {"typed_chars": 400, "keystrokes": 400, "active_typing_seconds": 10}, "", 30)
        self.assertTrue(any("faster than human" in s for s in r.signals))
