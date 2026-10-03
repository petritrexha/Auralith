"""'Explain it in your own words' comprehension checks.

1. `start_check(card)` asks the model for ONE question about the developer's own code (why / what-if,
   not a definition) plus the key points a good answer should hit.
2. `submit_check(check, answer, telemetry)` grades the answer with a rubric, runs the anti-AI integrity
   assessment, and — only when the answer passes AND integrity is clean — marks the concept as verified.

Mock mode (no API key) uses catalog-based questions and keyword grading so the flow demos offline.
"""
from __future__ import annotations

import re

from django.utils import timezone

from core.models import Card, ComprehensionCheck, UserConcept
from core.services import integrity, knowledge

from . import catalog
from .llm import ai_mode, complete_json

PASS_AT = 70
PARTIAL_AT = 45
MAX_ATTEMPTS_PER_DAY = 3
GRACE_SECONDS = 20

QUESTION_SYSTEM = """You write one comprehension question for a developer about code an AI agent just wrote in THEIR project.
Rules:
- Ask about *why* or *what would happen if* — reasoning, not a definition. It must be impossible to answer well without understanding the concept.
- Refer to their actual file / code (by name) so a generic textbook answer doesn't fit.
- Answerable in 3-5 sentences of plain language. One question only (it may have two short parts).
- Friendly tone. No trick questions.
Return JSON: {"question": str, "key_points": [3-4 short strings a good answer must cover]}"""

GRADE_SYSTEM = """You grade a developer's answer to a comprehension question about code in their project.
Score with this rubric (be fair, ignore spelling/grammar, accept informal language and imperfect English):
- correctness 0-50: is the explanation of the concept right?
- application 0-30: does it connect to THEIR code / the situation in the question?
- reasoning 0-20: does it show their own understanding (cause and effect, what breaks) rather than buzzwords?
Also estimate ai_style_likelihood 0-1: how likely the text was written by an AI assistant rather than typed by a person
in a hurry (AI tells: polished structure, hedging phrases, lists, perfect grammar for a casual answer). Be conservative.
Return JSON: {"correctness": int, "application": int, "reasoning": int, "feedback": "2 encouraging sentences: what was good, what to add",
"missed_points": [strings], "ai_style_likelihood": float}"""


class CheckError(Exception):
    pass


def attempts_today(user, card: Card) -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return ComprehensionCheck.objects.filter(user=user, card=card, started_at__gte=start).count()


def _mock_question(card: Card) -> tuple[str, list[str]]:
    fname = (card.file_path or "your code").replace("\\", "/").split("/")[-1]
    entry = catalog.BY_SLUG.get(card.concept.slug)
    key_points = list(entry.keywords) if entry else []
    if entry:
        # Use the most distinctive words from the curated summary as the grading key.
        words = [w for w in re.findall(r"[a-zA-Z]{6,}", entry.summary.lower())]
        key_points = list(dict.fromkeys(key_points + words))[:8]
    question = (
        f"In your own words: what does {card.concept.name} do in `{fname}`, "
        f"and what would go wrong if it was removed or done incorrectly?"
    )
    return question, key_points


def start_check(user, card: Card) -> ComprehensionCheck:
    if card.user_id != user.id:
        raise CheckError("not your card")
    if attempts_today(user, card) >= MAX_ATTEMPTS_PER_DAY:
        raise CheckError(f"You've used today's {MAX_ATTEMPTS_PER_DAY} attempts for this card. Try again tomorrow — sleep helps memory!")
    mode = ai_mode()
    question, key_points = None, []
    if mode == "live":
        data, _ = complete_json(
            QUESTION_SYSTEM,
            f"Concept: {card.concept.name}\nFile: {card.file_path}\nWhat the card told them: {card.summary}\n"
            f"Why it's in their code: {card.why_here}\nSnippet:\n{card.code_snippet[:1500]}",
            max_tokens=400,
        )
        if data and isinstance(data.get("question"), str):
            question = data["question"].strip()[:600]
            key_points = [str(k)[:120] for k in (data.get("key_points") or [])][:5]
    if not question:
        question, key_points = _mock_question(card)
        mode = "mock"
    return ComprehensionCheck.objects.create(user=user, card=card, question=question, key_points=key_points, mode=mode)


def _mock_grade(check: ComprehensionCheck, answer: str) -> dict:
    text = answer.lower()
    keys = [k.lower() for k in check.key_points] or ["because"]
    hits = [k for k in keys if k in text]
    coverage = len(hits) / len(keys)
    words = len(re.findall(r"\w+", answer))
    reasoning_words = len(re.findall(r"\b(because|so|otherwise|if|without|would|breaks?|prevents?|means|then)\b", text))
    fname = (check.card.file_path or "").replace("\\", "/").split("/")[-1].lower()
    applies = bool(fname and fname.split(".")[0] in text) or "my " in text or "our " in text or "here" in text
    correctness = int(min(50, 15 + coverage * 70)) if words >= 12 else int(coverage * 25)
    application = 25 if applies else (12 if words >= 25 else 5)
    reasoning = min(20, reasoning_words * 5)
    missed = [k for k in keys[:4] if k not in hits][:3]  # curated keywords come first
    return {
        "correctness": correctness, "application": application, "reasoning": reasoning,
        "feedback": "Thanks for explaining it in your own words. "
        + ("Nice — you connected it to your own code." if applies else "Try to say what it does in *your* file specifically."),
        "missed_points": missed, "ai_style_likelihood": None,
    }


def submit_check(check: ComprehensionCheck, answer: str, telemetry: dict) -> ComprehensionCheck:
    if check.status != ComprehensionCheck.Status.OPEN:
        raise CheckError("This check was already submitted.")
    now = timezone.now()
    elapsed = (now - check.started_at).total_seconds()
    answer = (answer or "").strip()[:4000]
    check.answer, check.submitted_at, check.telemetry = answer, now, telemetry or {}

    if elapsed > check.time_limit_seconds + GRACE_SECONDS:
        check.status = ComprehensionCheck.Status.EXPIRED
        check.feedback = "Time ran out — no stress, start a new check when you're ready."
        check.save()
        return check

    grade = None
    if check.mode == "live" and ai_mode() == "live" and len(answer) >= 10:
        grade, _ = complete_json(
            GRADE_SYSTEM,
            f"Concept: {check.card.concept.name}\nFile: {check.card.file_path}\nQuestion: {check.question}\n"
            f"Key points a good answer covers: {check.key_points}\nSnippet:\n{check.card.code_snippet[:1200]}\n\n"
            f"Developer's answer (typed by hand):\n\"\"\"{answer}\"\"\"",
            max_tokens=500,
        )
    if not grade:
        grade = _mock_grade(check, answer)

    def clamp(v, hi):
        try:
            return max(0, min(hi, int(v)))
        except (TypeError, ValueError):
            return 0

    rubric = {"correctness": clamp(grade.get("correctness"), 50), "application": clamp(grade.get("application"), 30),
              "reasoning": clamp(grade.get("reasoning"), 20)}
    check.rubric = rubric
    check.score = sum(rubric.values()) if len(answer) >= 10 else 0
    check.feedback = str(grade.get("feedback") or "")[:600]
    check.missed_points = [str(m)[:160] for m in (grade.get("missed_points") or [])][:4]

    likelihood = grade.get("ai_style_likelihood")
    try:
        likelihood = float(likelihood) if likelihood is not None else None
    except (TypeError, ValueError):
        likelihood = None
    result = integrity.assess(answer, check.telemetry, f"{check.card.summary}\n{check.card.why_here}", elapsed, likelihood)
    check.suspicion, check.integrity, check.integrity_signals = result.suspicion, result.level, result.signals

    S = ComprehensionCheck.Status
    if check.score >= PASS_AT:
        check.status = S.PASSED if result.level != "flagged" else S.UNVERIFIED
    elif check.score >= PARTIAL_AT:
        check.status = S.PARTIAL
    else:
        check.status = S.FAILED
    check.save()

    if check.status == S.PASSED and result.level == "clean":
        uc = knowledge.set_status(check.user, check.card.concept, UserConcept.Status.KNOWN)
        uc.verified_at = now
        uc.save(update_fields=["verified_at"])
    elif check.status == S.PASSED:  # passed, but some signals → known, pending review, not verified
        knowledge.set_status(check.user, check.card.concept, UserConcept.Status.KNOWN)
    return check
