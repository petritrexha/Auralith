"""The LearnLoop teaching agent.

Given the code changes a coding agent just made, decide what (if anything) is worth teaching
this specific person, and write short "why it's here, in your code" cards.

It's a real tool-using agent, not a fixed pipeline:
  - it checks the person's knowledge profile before deciding,
  - it can read a full diff when the overview isn't enough,
  - it looks up trusted docs and verifies links,
  - it explicitly records skipped concepts and why (shown in the admin trace).

Without an API key it falls back to a deterministic mock agent with the same contract,
so the plugin, API and dashboards can be built and demoed offline.
"""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.models import AnalyzeLog, Card
from core.services import knowledge
from core.services.scrub import is_secret_file, scrub_text

from . import catalog
from .llm import ai_mode, run_tool_loop

log = logging.getLogger("core.agent")

TRIVIAL_MIN_ADDED_LINES = 3


# ---------------------------------------------------------------------------
# Input preparation
# ---------------------------------------------------------------------------
def added_lines(diff: str) -> list[str]:
    lines = diff.splitlines()
    plus = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
    return plus if plus else lines  # raw content (no diff markers) counts as all added


def prepare_changes(changes: list[dict]) -> tuple[list[dict], list[str]]:
    """Scrub secrets, drop secret files, merge per file, cap sizes."""
    cfg = settings.LEARNLOOP
    merged: dict[str, str] = {}
    skipped: list[str] = []
    for ch in changes or []:
        path = str(ch.get("file") or "").strip()[:500]
        diff = str(ch.get("diff") or "")
        if not path or not diff.strip():
            continue
        if is_secret_file(path):
            skipped.append(path)
            continue
        merged[path] = (merged.get(path, "") + "\n" + diff).strip()
    prepared = []
    for path, diff in list(merged.items())[: cfg["MAX_FILES_PER_CALL"]]:
        diff = scrub_text(diff)[: cfg["MAX_DIFF_CHARS_PER_FILE"]]
        prepared.append({"file": path, "diff": diff, "added": len(added_lines(diff))})
    return prepared, skipped


def snippet_from(diff: str, around: int | None = None, max_lines: int = 8) -> str:
    lines = added_lines(diff)
    if around is None:
        start = 0
    else:
        start = max(0, min(around, len(lines) - 1) - 2)
    return "\n".join(lines[start : start + max_lines]).strip()


# ---------------------------------------------------------------------------
# Shared state + card saving (used by both live and mock agents)
# ---------------------------------------------------------------------------
@dataclass
class AnalyzeContext:
    user: object
    profile: object
    session_id: str
    changes: list[dict]
    agent_message: str
    cards_left: int
    created: list[Card] = field(default_factory=list)
    concepts_considered: set[str] = field(default_factory=set)
    trace: list[dict] = field(default_factory=list)

    def change_for(self, path: str) -> dict | None:
        for ch in self.changes:
            if ch["file"] == path or ch["file"].endswith(path) or path.endswith(ch["file"]):
                return ch
        return None


def save_card(ctx: AnalyzeContext, data: dict, *, doc_verified: bool = False) -> dict:
    name = str(data.get("concept_name") or "").strip()
    if not name:
        return {"ok": False, "error": "concept_name is required"}
    slug = knowledge.normalize_slug(data.get("slug") or name)
    ctx.concepts_considered.add(slug)
    if ctx.cards_left <= 0:
        return {"ok": False, "error": "card limit reached for this turn — stop creating cards"}
    if knowledge.is_blocked(ctx.user, slug):
        return {"ok": False, "error": f"user already knows or muted '{slug}' — skip it"}
    if any(c.concept.slug == slug for c in ctx.created):
        return {"ok": False, "error": "a card for this concept was already created in this turn"}

    file_path = str(data.get("file_path") or "")[:500]
    change = ctx.change_for(file_path) if file_path else (ctx.changes[0] if ctx.changes else None)
    snippet = str(data.get("code_snippet") or "").strip()
    if not snippet and change:
        snippet = snippet_from(change["diff"])
    snippet = scrub_text("\n".join(snippet.splitlines()[:15]))

    concept = knowledge.get_or_create_concept(name, slug, str(data.get("category") or "other"))
    knowledge.record_exposure(ctx.user, concept)
    card = Card.objects.create(
        user=ctx.user,
        concept=concept,
        summary=str(data.get("summary") or "").strip()[:1200],
        why_here=str(data.get("why_here") or "").strip()[:800],
        diagram_mermaid=str(data.get("diagram_mermaid") or "").strip()[:1500],
        doc_url=str(data.get("doc_url") or "").strip()[:500],
        doc_verified=doc_verified,
        code_snippet=snippet,
        file_path=(change["file"] if change else file_path),
        session_id=ctx.session_id[:120],
    )
    ctx.created.append(card)
    ctx.cards_left -= 1
    return {"ok": True, "card_id": card.pk, "cards_left": ctx.cards_left}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
def verify_link(url: str) -> dict:
    """HEAD (then GET) a URL with a short timeout. Cached for a day."""
    if not re.match(r"^https://", url or ""):
        return {"ok": False, "reason": "only https links are allowed"}
    if any(url.startswith(e.doc_url) for e in catalog.CATALOG):
        return {"ok": True, "status": 200, "trusted": True}
    if not settings.LEARNLOOP["VERIFY_LINKS"]:
        return {"ok": True, "status": None, "note": "link verification disabled"}
    key = "ll:link:" + url[:200]
    hit = cache.get(key)
    if hit is not None:
        return hit
    result = {"ok": False, "status": None}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "LearnLoop-link-check/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                result = {"ok": 200 <= resp.status < 400, "status": resp.status}
                break
        except urllib.error.HTTPError as exc:
            result = {"ok": False, "status": exc.code}
            if exc.code not in (403, 405):
                break
        except Exception as exc:  # DNS, timeout, TLS…
            result = {"ok": False, "status": None, "reason": type(exc).__name__}
            break
    cache.set(key, result, 60 * 60 * 24)
    return result


TOOLS = [
    {
        "name": "check_user_knowledge",
        "description": "Look up this developer's status for candidate concepts. Returns never_seen | new | seen | known | muted and how often they've seen it. Call this ONCE with all candidates before creating cards.",
        "input_schema": {
            "type": "object",
            "properties": {"slugs": {"type": "array", "items": {"type": "string"}, "description": "kebab-case concept slugs, e.g. jwt-refresh-rotation"}},
            "required": ["slugs"],
        },
    },
    {
        "name": "read_full_diff",
        "description": "Read the complete (secret-scrubbed) diff for one file when the overview was truncated or you need more context for 'why it's here'.",
        "input_schema": {"type": "object", "properties": {"file": {"type": "string"}}, "required": ["file"]},
    },
    {
        "name": "find_docs",
        "description": "Search LearnLoop's curated catalog of official documentation. Prefer these links over URLs from memory.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "verify_link",
        "description": "Check that a documentation URL you want to use actually resolves (https only). Only needed for URLs that did not come from find_docs.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "create_card",
        "description": "Save a learning card for the developer. Max cards per turn is given in the instructions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "concept_name": {"type": "string", "description": "Human name, e.g. 'JWT refresh token rotation'"},
                "slug": {"type": "string", "description": "kebab-case id, stable across users"},
                "category": {"type": "string", "enum": ["auth", "database", "frontend", "api", "devops", "testing", "security", "other"]},
                "summary": {"type": "string", "description": "3-4 plain sentences: what the concept is and why people use it."},
                "why_here": {"type": "string", "description": "1-2 sentences tying it to THIS code: which file/function and what it does here."},
                "file_path": {"type": "string"},
                "code_snippet": {"type": "string", "description": "<=10 lines copied from the diff that show the concept."},
                "doc_url": {"type": "string"},
                "diagram_mermaid": {"type": "string", "description": "Optional tiny Mermaid diagram (graph LR / sequenceDiagram), max ~6 nodes."},
            },
            "required": ["concept_name", "slug", "category", "summary", "why_here", "file_path"],
        },
    },
    {
        "name": "skip_concept",
        "description": "Record a concept you noticed but decided NOT to teach (too basic for this person, already known, not really used). Helps the manager trace.",
        "input_schema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["slug", "reason"],
        },
    },
]

SYSTEM_PROMPT = """You are LearnLoop, a teaching agent that runs beside an AI coding agent inside a company.
Your job: when the coding agent changes code, decide what the human developer should understand about it,
and write short, encouraging cards that explain the concept *in their code*. You protect the business from
"comprehension debt": code that ships but nobody on the team understands.

Developer skill level: {skill}
Concepts this developer already knows or muted (never teach these): {known}
Whole topics they ticked as known on their skill checklist (never teach anything inside these): {topics}
Cards you may create this turn: {cards_left}

How to work:
1. Read the changes. List 1-3 candidate concepts that are genuinely *used* in the new code (patterns, techniques,
   APIs, security or data-integrity practices). Ignore renames, formatting, copy changes and trivial syntax.
2. Call check_user_knowledge once with all candidate slugs (and find_docs in the same turn if useful).
3. Decide. Skip anything known/muted, and anything a {skill} developer would certainly already know
   (for a beginner: still skip variables, loops, if/else, basic HTML tags, imports). Prefer concepts with
   business risk if misunderstood (auth, security, data integrity, money, performance). Use skip_concept for
   each candidate you drop, with a short reason.
4. Create at most {cards_left} card(s) with create_card, all in the same turn. "why_here" must reference the
   actual file and what the code does there. Copy a short real snippet from the diff. Use a doc link from
   find_docs, or verify_link any other URL; omit doc_url rather than guess.
5. If nothing is worth teaching, just skip everything — zero cards is a fine outcome.

Tone: calm, smart, slightly playful tutor. Never shaming ("you don't know X"); say things like "new this session".
Be concise. Do not ask questions; you are running unattended."""


def _overview(changes: list[dict], agent_message: str, per_file: int = 2500, total: int = 12000) -> str:
    parts, used = [], 0
    for ch in changes:
        body = ch["diff"][:per_file]
        truncated = " (truncated — use read_full_diff)" if len(ch["diff"]) > per_file else ""
        block = f"### {ch['file']}{truncated}\n```diff\n{body}\n```"
        if used + len(block) > total:
            parts.append(f"### {ch['file']} (not shown — use read_full_diff)")
            continue
        parts.append(block)
        used += len(block)
    msg = "Here are the changes the coding agent just made:\n\n" + "\n\n".join(parts)
    if agent_message:
        msg += "\n\nThe coding agent's own summary of what it did (use it to explain *why*):\n" + agent_message[:2000]
    return msg


def _run_live(ctx: AnalyzeContext, deadline: float):
    cfg = settings.LEARNLOOP

    def check_user_knowledge(inp):
        slugs = [str(s) for s in (inp.get("slugs") or [])][:6]
        ctx.concepts_considered.update(knowledge.normalize_slug(s) for s in slugs)
        return knowledge.statuses_for(ctx.user, slugs)

    def read_full_diff(inp):
        ch = ctx.change_for(str(inp.get("file") or ""))
        return {"file": ch["file"], "diff": ch["diff"]} if ch else {"error": "file not in this batch"}

    def find_docs(inp):
        return [{"name": e.name, "slug": e.slug, "doc_url": e.doc_url, "level": e.level} for e in catalog.search(str(inp.get("query") or ""))]

    def verify(inp):
        return verify_link(str(inp.get("url") or ""))

    def create_card(inp):
        url = str(inp.get("doc_url") or "")
        verified = bool(url) and verify_link(url).get("ok", False)
        if url and not verified:
            inp = {**inp, "doc_url": ""}  # never show a broken link
        return save_card(ctx, inp, doc_verified=verified)

    def skip_concept(inp):
        slug = knowledge.normalize_slug(str(inp.get("slug") or ""))
        ctx.concepts_considered.add(slug)
        return {"ok": True}

    system = SYSTEM_PROMPT.format(
        skill=ctx.profile.skill_level,
        known=", ".join(knowledge.known_slugs(ctx.user)) or "(none yet)",
        topics="; ".join(knowledge.known_topic_names(ctx.user)) or "(none)",
        cards_left=ctx.cards_left,
    )
    return run_tool_loop(
        system=system,
        user_message=_overview(ctx.changes, ctx.agent_message),
        tools=TOOLS,
        handlers={
            "check_user_knowledge": check_user_knowledge,
            "read_full_diff": read_full_diff,
            "find_docs": find_docs,
            "verify_link": verify,
            "create_card": create_card,
            "skip_concept": skip_concept,
        },
        max_turns=cfg["MAX_AGENT_TURNS"],
        deadline=deadline,
        should_stop=lambda: ctx.cards_left <= 0,
    )


def _run_mock(ctx: AnalyzeContext):
    """Offline stand-in with the same decisions the live agent makes, driven by the catalog."""
    from .llm import AgentRun

    run = AgentRun()
    candidates = []  # (entry, change, line)
    for ch in ctx.changes:
        text = "\n".join(added_lines(ch["diff"]))
        for entry in catalog.detect(text):
            if entry.slug not in {c[0].slug for c in candidates}:
                candidates.append((entry, ch, entry.first_match_line(text)))
    candidates = candidates[:3]
    slugs = [c[0].slug for c in candidates]
    statuses = knowledge.statuses_for(ctx.user, slugs) if slugs else {}
    ctx.concepts_considered.update(slugs)
    run.trace.append({"type": "tool", "tool": "check_user_knowledge", "input": {"slugs": slugs}, "result": statuses})

    level_rank = {"basic": 0, "intermediate": 1, "advanced": 2}
    risky = {"auth", "security", "database"}
    # Teach riskier and more advanced things first, like the live agent is told to.
    candidates.sort(key=lambda c: (c[0].category in risky, level_rank[c[0].level]), reverse=True)
    for entry, ch, line in candidates:
        info = statuses.get(entry.slug, {})
        status = info.get("status")
        if status in ("known", "muted"):
            reason = f"covered by checklist topic '{info['covered_by']}'" if info.get("covered_by") else f"user marked it {status}"
            run.trace.append({"type": "tool", "tool": "skip_concept", "input": {"slug": entry.slug, "reason": reason}})
            continue
        if ctx.profile.skill_level == "intermediate" and entry.level == "basic":
            run.trace.append({"type": "tool", "tool": "skip_concept", "input": {"slug": entry.slug, "reason": "too basic for an intermediate developer"}})
            continue
        if ctx.cards_left <= 0:
            run.trace.append({"type": "tool", "tool": "skip_concept", "input": {"slug": entry.slug, "reason": "card limit reached this turn"}})
            continue
        fname = ch["file"].replace("\\", "/").split("/")[-1]
        if status in (None, "never_seen"):
            why = f"New this session: the agent used {entry.name} in `{fname}` — the snippet below shows where."
        else:
            why = f"You've met {entry.name} before — it shows up again in `{fname}`. Worth a second look."
        result = save_card(
            ctx,
            {
                "concept_name": entry.name, "slug": entry.slug, "category": entry.category,
                "summary": entry.summary, "why_here": why, "file_path": ch["file"],
                "code_snippet": snippet_from(ch["diff"], line), "doc_url": entry.doc_url,
                "diagram_mermaid": entry.diagram,
            },
            doc_verified=True,
        )
        run.trace.append({"type": "tool", "tool": "create_card", "input": {"slug": entry.slug}, "result": result})
    if not candidates:
        run.trace.append({"type": "thought", "text": "Nothing new or interesting in these changes."})
    return run


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def analyze(user, session_id: str, changes: list[dict], agent_message: str = "") -> tuple[list[Card], AnalyzeLog]:
    cfg = settings.LEARNLOOP
    started = time.monotonic()
    deadline = started + cfg["ANALYZE_BUDGET_SECONDS"]
    profile = knowledge.get_profile(user)
    profile.last_active_at = timezone.now()
    profile.save(update_fields=["last_active_at"])

    prepared, skipped_files = prepare_changes(changes)
    mode = ai_mode()
    log_row = AnalyzeLog(user=user, session_id=session_id[:120], files_count=len(prepared), mode=mode)
    trace: list[dict] = []
    cards: list[Card] = []
    if skipped_files:
        trace.append({"type": "scrub", "skipped_secret_files": skipped_files})

    daily_left = max(profile.daily_card_limit - profile.cards_today(), 0)
    if daily_left <= 0:
        log_row.outcome, log_row.mode = "daily_limit", "skipped"
    elif not prepared or sum(c["added"] for c in prepared) < TRIVIAL_MIN_ADDED_LINES:
        log_row.outcome, log_row.mode = "trivial", "skipped"
    else:
        ctx = AnalyzeContext(
            user=user, profile=profile, session_id=session_id, changes=prepared,
            agent_message=scrub_text(agent_message or ""), cards_left=min(cfg["MAX_CARDS_PER_CALL"], daily_left),
        )
        run = _run_live(ctx, deadline) if mode == "live" else _run_mock(ctx)
        trace.extend(run.trace)
        log_row.llm_calls = run.usage.calls
        log_row.input_tokens = run.usage.input_tokens
        log_row.output_tokens = run.usage.output_tokens
        log_row.concepts_found = len(ctx.concepts_considered)
        log_row.outcome = {"error": "error", "budget": "budget"}.get(run.stopped_by, "ok")
        log_row.cards_returned = len(ctx.created)
        cards = ctx.created

    log_row.duration_ms = int((time.monotonic() - started) * 1000)
    log_row.trace = trace
    log_row.save()
    return cards, log_row
