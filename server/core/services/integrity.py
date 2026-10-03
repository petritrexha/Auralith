"""Anti-AI integrity signals for comprehension checks.

No AI-text detector is reliable on its own, so we combine *process* signals (how the answer
was produced) with lighter *text* signals. The result is a suspicion score, never an automatic
"cheater" label: a suspicious answer simply doesn't count as verified, and an admin can review it.

Process signals come from the check page (paste blocked + counted, keystrokes, focus changes,
timing). Text signals are computed here (copying the card, AI-style phrasing) plus an optional
"AI-style likelihood" from the grading model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

REVIEW_AT = 30
FLAG_AT = 60

AI_PHRASES = [
    r"\bit'?s (important|worth) (to note|noting)\b",
    r"\bin (summary|conclusion)\b",
    r"\bfurthermore\b",
    r"\bmoreover\b",
    r"\badditionally\b",
    r"\boverall,",
    r"\bensures? that\b",
    r"\bplays a (crucial|key|vital) role\b",
    r"\bleverag(e|es|ing)\b",
    r"\bseamless(ly)?\b",
    r"\brobust\b",
    r"\bdelve\b",
    r"\bas an ai\b",
    r"\bcertainly!",
    r"\bgreat question\b",
]
_ai_res = [re.compile(p, re.IGNORECASE) for p in AI_PHRASES]
STOP = set("the a an and or of to in is it that this for on with as be are was by at from you your if not can will when what why how".split())


@dataclass
class IntegrityResult:
    suspicion: int = 0
    level: str = "clean"  # clean | review | flagged
    signals: list[str] = field(default_factory=list)


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", (text or "").lower()) if w not in STOP]


def copy_overlap(answer: str, source: str, n: int = 5) -> float:
    """Share of the answer's 5-word sequences that appear verbatim in the card text (parroting)."""
    a, s = _words(answer), _words(source)
    if len(a) < n or len(s) < n:
        return 0.0
    grams_s = {tuple(s[i : i + n]) for i in range(len(s) - n + 1)}
    grams_a = [tuple(a[i : i + n]) for i in range(len(a) - n + 1)]
    return sum(g in grams_s for g in grams_a) / len(grams_a)


def style_markers(answer: str) -> list[str]:
    found = [r.pattern for r in _ai_res if r.search(answer or "")]
    if (answer or "").count("—") >= 2:
        found.append("em-dashes")
    if re.search(r"^\s*([-*•]|\d+\.)\s", answer or "", re.MULTILINE) and len((answer or "").splitlines()) >= 3:
        found.append("list formatting")
    if re.search(r"\*\*[^*]+\*\*|^#+\s", answer or "", re.MULTILINE):
        found.append("markdown formatting")
    return found


def assess(answer: str, telemetry: dict, card_text: str, elapsed_seconds: float, ai_style_likelihood: float | None = None) -> IntegrityResult:
    t = telemetry or {}
    res = IntegrityResult()
    length = len((answer or "").strip())
    keystrokes = int(t.get("keystrokes") or 0)
    typed_chars = int(t.get("typed_chars") or 0)
    paste_attempts = int(t.get("paste_attempts") or 0)
    blur_count = int(t.get("blur_count") or 0)
    hidden_seconds = float(t.get("hidden_seconds") or 0)
    active_seconds = max(float(t.get("active_typing_seconds") or 0), 1.0)

    def add(points: int, reason: str):
        res.suspicion += points
        res.signals.append(reason)

    if not t:
        add(35, "No typing data was received (page script blocked or answer sent directly).")
    else:
        if paste_attempts:
            add(min(15 * paste_attempts, 30), f"Tried to paste {paste_attempts} time(s) (paste is disabled).")
        # Text that appears without matching keystrokes = injected (extension, devtools, autofill).
        if length > 40 and typed_chars < length * 0.7:
            add(40, f"Only {typed_chars} characters were typed for a {length}-character answer.")
        cps = typed_chars / active_seconds
        if typed_chars > 80 and cps > 12:
            add(20, f"Typing speed of {cps:.0f} chars/second is faster than human typing.")
        if hidden_seconds > 60:
            add(35, f"Left the page for {hidden_seconds:.0f}s during the check.")
        elif hidden_seconds > 15 or blur_count >= 3:
            add(12, f"Switched away from the page {blur_count} time(s) ({hidden_seconds:.0f}s total).")
        if length > 120 and elapsed_seconds < 25:
            add(15, f"A {length}-character answer was submitted after only {elapsed_seconds:.0f}s.")
        if keystrokes and length and keystrokes < length * 0.5:
            add(10, "Very few key presses for the length of the answer.")

    overlap = copy_overlap(answer, card_text)
    if overlap > 0.35:
        add(20, f"{int(overlap * 100)}% of the answer repeats the card text word for word.")

    markers = style_markers(answer)
    if len(markers) >= 2:
        add(10, f"AI-style phrasing ({len(markers)} markers).")
    if ai_style_likelihood is not None and ai_style_likelihood >= 0.75:
        add(15, f"The grader rated the writing style as likely AI-generated ({ai_style_likelihood:.0%}).")

    res.suspicion = min(res.suspicion, 100)
    res.level = "flagged" if res.suspicion >= FLAG_AT else "review" if res.suspicion >= REVIEW_AT else "clean"
    return res
