# LearnLoop — context for Claude Code

Hackathon project (Genpact hackathon, track **"AI agentic for businesses"**). Team lead: Alban. Started in a Claude Cowork chat; this file carries that context over.

## Pitch
"Businesses are handing their code to AI agents. LearnLoop is the agent that makes sure their people still understand it, and shows managers where the gaps are."
One-liner: *Learn what your AI just built, while it builds it.* Core metric: **comprehension debt** (concepts surfaced vs understood).
Buyer = engineering manager/CTO. The admin dashboard, risk hotspots and manager briefing are the business story; the dev-facing cards are the hook.
Differentiator vs Unvibe (unvibe.site, manual select + Cmd+U explainer): LearnLoop runs automatically inside the agent loop, knows *why* the agent changed code (gets `last_assistant_message`), personalizes per user knowledge, and gives managers org-level visibility.

## Architecture
- `plugin/` — Claude Code plugin, Python stdlib only. Hooks: `SessionStart` → `ping.py` (async), `PostToolUse` (Edit|Write|MultiEdit|NotebookEdit) → `collect.py` (no network, scrubs secrets, appends diff to `$CLAUDE_PLUGIN_DATA/batches/<session>.jsonl`), `Stop` → `flush.py` (POST /api/v1/analyze, prints `{"systemMessage": ...}` so cards show to the user only and add nothing to the agent's context). Config via plugin `userConfig` (`CLAUDE_PLUGIN_OPTION_SERVER_URL`, `CLAUDE_PLUGIN_OPTION_API_TOKEN`) or env `LEARNLOOP_URL` / `LEARNLOOP_TOKEN`. Scripts must ALWAYS exit 0 and never break a session.
- `server/` — Django 5.1, SQLite, server-rendered templates (placeholder styling; UI team restyles).
  - `core/agent/analyzer.py` — teaching agent: Haiku tool-use loop (`check_user_knowledge`, `read_full_diff`, `find_docs`, `verify_link`, `create_card`, `skip_concept`), max 2 cards, ~12s budget, trace saved to `AnalyzeLog.trace` (shown at `/manage/activity/`).
  - `core/agent/reporter.py` — manager agent: weekly briefing (`get_org_overview`, `get_hotspots`, `get_people_needing_support`, `get_concept_details`, `write_report`). CLI: `python manage.py team_report`.
  - `core/agent/catalog.py` — curated concepts + official doc links; drives `find_docs` and the offline **mock mode** (used when `ANTHROPIC_API_KEY` is empty or `LEARNLOOP_MOCK_AI=1`).
  - `core/agent/llm.py` — generic tool loop + usage tracking.
  - `core/services/` — `knowledge.py` (concept slugs, statuses), `checklist.py` (skill map on /app/concepts/: 7 areas → 45 general topics → 231 niche skills; a ticked item is a known Concept with slug prefix `stack-` whose regex patterns block matching concepts; levels + encouragement shown on the dashboard; `UserConcept.objects.from_work()` keeps self-reported ticks out of stats), `insights.py` (member/org stats, hotspots, needs_attention), `accounts.py` (admin-only account creation), `scrub.py` (keep in sync with `plugin/scripts/learnloop_common.py`).
  - Card style: `/app/personalize/` sets `Profile.explanation_depth` (brief/standard/deep), `show_diagrams`, `use_analogies`, `terminal_detail` (compact/visual/link). Rules go into the analyzer prompt (`preference_rules`) AND are enforced in `card_style()`. `core/services/visuals.py` sanitizes Mermaid and turns it into terminal text flows; catalog entries carry diagram + pitfall + analogy (`VISUALS`). Shared renderer: `templates/core/_mermaid.html`.
  - `core/api.py` — `/api/v1/ping`, `/api/v1/analyze` (Bearer token, hashed in DB, per-user hourly rate limit). Plugin sends `ack` (card ids it displayed); unacked recent cards are re-sent next call, so cards that finish after the plugin's 20s wait still reach the terminal.
  - Commands: `seed_demo [--reset]`, `create_member <email> [--admin]`, `team_report`.
- `vscode-extension/` — VS Code extension (plain JS, no deps): sidebar of cards, card webview, CodeLens, notifications, status bar. Uses `/api/v1/cards` + `/api/v1/cards/<id>/action` with the plugin token. F5 via `.vscode/launch.json`; package with `npx @vscode/vsce package --allow-missing-repository`. See its README.
- `.claude-plugin/marketplace.json` — install with `/plugin marketplace add <repo path>` then `/plugin install learnloop@learnloop`.

## Rules / conventions
- RBAC: no public signup; members only see their own data (always filter by `request.user`, 404 otherwise); `/manage/*` is staff-only.
- Never store full diffs; cards keep a short scrubbed snippet. Tokens shown once, stored as SHA-256.
- Get fresh profiles via `knowledge.get_profile(user)` — a cached `user.profile` can be stale and overwrite the token hash on `save()`.
- Rate limit + "connected" indicator use locmem cache → single process only (switch CACHES to DB/Redis for multi-worker).
- Run tests: `python manage.py test core` (36 tests, include a fake-Anthropic tool-loop test). Django 5.1 + Python 3.14: test-client tests error on `Context.__copy__`; upgrade to Django 5.2.8+ or run on Python 3.13.
- Dev machine is Windows + PowerShell 5: no `&&`; activate venv with `.venv\Scripts\Activate.ps1`.

## Status (Oct 3, 2026)
Done: backend, both agents (mock + live code path), plugin, basic pages, tests, demo seed. Demo runs locally.
Not yet verified: live run against the real Anthropic API; plugin installed in a real Claude Code session on Windows.

## Next steps (priority order)
1. Add `ANTHROPIC_API_KEY` to `server/.env`, do a real end-to-end run, tune `SYSTEM_PROMPT` in analyzer.py on real diffs.
2. Install the plugin in Claude Code on Windows and confirm hooks fire + `systemMessage` cards appear (check `python3`/`python` on PATH; `LEARNLOOP_DEBUG=1` logs to the plugin data dir).
3. UI polish per design brief (Linear/Vercel look, dark default, one accent): dashboards, card detail, animated landing terminal.
4. Demo script for judges: dev codes → card appears → mark known → admin dashboard hotspots → generate briefing → agent activity trace.
5. Stretch: quizzes, weekly digest email, YouTube/video links, Redis cache, deploy (HTTPS, DEBUG=0).

## Comprehension checks (verified understanding + anti-AI) — added Oct 3
- Card page → "Prove it": one "explain it in your own words" question about the user's own code (core/agent/checker.py: start_check / submit_check). Live = Haiku writes the question + grades with a rubric (correctness 50, applies to their code 30, own reasoning 20); mock = catalog keywords.
- Pass >= 70 AND clean integrity → UserConcept.verified_at set ("verified", separate from self-reported "I know this"/checklist ticks). set_status() clears verified_at when status leaves KNOWN.
- Anti-AI (core/services/integrity.py): check.html blocks paste/drop and sends typing telemetry (keystrokes, typed_chars via beforeinput, paste attempts, blur/hidden time, active typing time). Signals: injected text (typed_chars << length), >12 chars/s, left page, no telemetry, copying the card (5-gram overlap), AI-style phrasing, grader's ai_style_likelihood. Score >=30 review, >=60 flagged. Never auto-fails: flagged pass = "unverified", admin reviews at /manage/checks/.
- Limits: 240s timer (+20s grace), 3 attempts per card per day. Model: ComprehensionCheck (migration 0004). Tests: CheckFlowTests, IntegrityTests in core/tests.py.
- Pitch: Anthropic's Jan 2026 study — AI users scored 50% vs 67% on comprehension; those who asked "why" kept their skills. LearnLoop makes that habit automatic and measurable.
