"""The manager agent: writes a weekly "comprehension briefing" for engineering leads.

It investigates the org's data with tools (overview, hotspots, people who need support,
concept drill-downs) and then writes a short, actionable report: where the team's
understanding lags behind what AI is shipping, and what to do about it this week.
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Concept, TeamReport, UserConcept
from core.services import insights

from .llm import AgentRun, ai_mode, run_tool_loop

User = get_user_model()

TOOLS = [
    {
        "name": "get_org_overview",
        "description": "Org-wide numbers: active users, cards, mastery rate, comprehension debt, most common concepts, per-category mastery, cost.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_hotspots",
        "description": "Code areas where AI introduced concepts that few people understand. Includes single-point-of-knowledge flags (bus factor).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_people_needing_support",
        "description": "Members with high exposure and low mastery, with their open concepts. Use for supportive suggestions, never ranking.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_concept_details",
        "description": "Who has been exposed to a concept and who understands it. Use to suggest pairing (someone who knows it teaches others).",
        "input_schema": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
    },
    {
        "name": "write_report",
        "description": "Save the final briefing. Call exactly once, at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body_markdown": {"type": "string", "description": "Markdown. Sections: Headline, Risk hotspots, Suggested actions this week (max 3, concrete: who/what/how long), Wins."},
            },
            "required": ["title", "body_markdown"],
        },
    },
]

SYSTEM = """You are LearnLoop's manager agent. Engineering leads use AI coding agents across their team and need to know
whether people still understand what is being shipped. Investigate the data with your tools, then write a short
weekly briefing with write_report.

Rules:
- Lead with the business risk: where would an incident or a code review hurt because nobody understands the code?
- Suggest at most 3 concrete actions (e.g. "30-min pairing: Ana (knows JWT rotation) with Ben and Dea on src/auth").
- Be supportive about people. Never rank or shame; frame as "could use support on X".
- Keep it under 250 words. Use real names, concepts and paths from the data. Do not invent numbers.
- Call several tools in the same turn when you can; finish with write_report."""


def concept_details(slug: str) -> dict:
    concept = Concept.objects.filter(slug=slug).first()
    if not concept:
        return {"error": "unknown concept"}
    rows = UserConcept.objects.filter(concept=concept).select_related("user")
    name = lambda u: u.get_full_name() or u.email or u.username  # noqa: E731
    return {
        "concept": concept.name,
        "category": concept.category,
        "understood_by": [name(r.user) for r in rows if r.status == UserConcept.Status.KNOWN],
        "still_learning": [name(r.user) for r in rows if r.status in (UserConcept.Status.NEW, UserConcept.Status.SEEN)],
    }


def _mock_report(days: int) -> tuple[str, str, dict]:
    org = insights.org_insights(days)
    hot = org["hotspots"][:3]
    people = org["needs_attention"][:3]
    lines = [
        f"**Headline:** the team saw {org['cards_period']} new concepts from AI-written code in the last {days} days; "
        f"org mastery is {int(org['org_mastery_rate'] * 100)}% and comprehension debt is {org['comprehension_debt']} open concepts.",
        "",
        "### Risk hotspots",
    ]
    lines += [
        f"- `{h['area']}`: {h['cards']} concepts surfaced, {int(h['understood_rate'] * 100)}% understood"
        + (" — **only one person understands this area**" if h["single_point_of_knowledge"] else "")
        + (f" (e.g. {', '.join(h['top_concepts'])})" if h["top_concepts"] else "")
        for h in hot
    ] or ["- No hotspots yet."]
    lines += ["", "### Suggested actions this week"]
    actions = []
    for h in hot[:2]:
        if not h["top_concepts"]:
            continue
        top = Concept.objects.filter(name=h["top_concepts"][0]).first()
        details = concept_details(top.slug) if top else {}
        teacher = (details.get("understood_by") or [None])[0]
        learners = details.get("still_learning", [])[:2]
        if teacher and learners:
            actions.append(f"- 30-min pairing on **{h['top_concepts'][0]}** in `{h['area']}`: {teacher} walks {', '.join(learners)} through it.")
        else:
            actions.append(f"- Short team walkthrough of **{h['top_concepts'][0]}** in `{h['area']}` before the next change there.")
    for p in people[:1]:
        if p["open_concepts"]:
            actions.append(f"- {p['name']} could use support on {', '.join(p['open_concepts'][:2])} — suggest reviewing their LearnLoop cards together.")
    lines += actions or ["- Keep going — nothing urgent this week."]
    learned = UserConcept.objects.filter(status=UserConcept.Status.KNOWN, known_at__gte=timezone.now() - timedelta(days=days)).count()
    lines += ["", "### Wins", f"- {learned} concepts marked as understood this period."]
    title = f"Team comprehension briefing — {timezone.localdate():%d %b %Y}"
    return title, "\n".join(lines), org


def generate_report(created_by=None, days: int = 7) -> TeamReport:
    mode = ai_mode()
    data = insights.org_insights(days)
    if mode == "mock":
        title, body, data = _mock_report(days)
        return TeamReport.objects.create(created_by=created_by, period_days=days, title=title, body_markdown=body, data=data, mode="mock")

    saved: dict = {}

    def write_report(inp):
        saved["title"] = str(inp.get("title") or "Team comprehension briefing")[:200]
        saved["body"] = str(inp.get("body_markdown") or "")
        return {"ok": True}

    handlers = {
        "get_org_overview": lambda _: {k: v for k, v in data.items() if k not in ("hotspots", "needs_attention")},
        "get_hotspots": lambda _: data["hotspots"],
        "get_people_needing_support": lambda _: data["needs_attention"],
        "get_concept_details": lambda inp: concept_details(str(inp.get("slug") or "")),
        "write_report": write_report,
    }
    run: AgentRun = run_tool_loop(
        system=SYSTEM,
        user_message=f"Write this week's briefing (period: last {days} days). Today is {timezone.localdate():%A %d %B %Y}.",
        tools=TOOLS,
        handlers=handlers,
        max_turns=6,
        deadline=time.monotonic() + 60,
        max_tokens=2000,
        should_stop=lambda: "body" in saved,
    )
    if "body" not in saved:  # model failed or ran out of time → still give the manager something
        title, body, _ = _mock_report(days)
        saved = {"title": title, "body": body + "\n\n_(Generated by the fallback writer.)_"}
    return TeamReport.objects.create(
        created_by=created_by, period_days=days, title=saved["title"], body_markdown=saved["body"],
        data=data, mode="live", trace=run.trace,
    )
