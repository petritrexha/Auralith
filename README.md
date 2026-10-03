# LearnLoop

**Learn what your AI just built, while it builds it.**

Businesses are handing their code to AI agents. LearnLoop is the agent that makes sure their people still understand it, and shows managers where the gaps are.

- **Claude Code plugin** (`plugin/`): quietly collects what the coding agent changes. At the end of each turn it shows a short "why it's here, in your code" card for anything new to *you*.
- **Teaching agent** (`server/core/agent/analyzer.py`): a Claude Haiku tool-use agent. It checks your knowledge profile, reads diffs, looks up and verifies docs, then decides what's worth teaching (usually 0–2 things).
- **Manager agent** (`server/core/agent/reporter.py`): looks into the org's data (risk hotspots, people who know a concept vs. people still learning it) and writes a weekly briefing with concrete actions.
- **Web app** (Django): member feed and knowledge profile, an admin org dashboard, and an agent activity trace.

```
learnloop/
├── .claude-plugin/marketplace.json   ← lets Claude Code install the plugin from this repo
├── plugin/                           ← Claude Code plugin (Python stdlib only)
│   ├── .claude-plugin/plugin.json
│   ├── hooks/hooks.json              ← SessionStart (ping), PostToolUse (collect), Stop (flush)
│   └── scripts/{collect,flush,ping,learnloop_common}.py
└── server/                           ← Django backend + API + agents
    ├── config/                       ← settings, urls
    └── core/
        ├── agent/                    ← analyzer (teaching agent), reporter (manager agent), catalog, llm loop
        ├── services/                 ← knowledge profile, insights, accounts, secret scrubbing
        ├── api.py                    ← /api/v1/ping, /api/v1/analyze
        ├── views.py + templates/     ← server-rendered learning workspace
        └── tests.py
```

## Run the server (5 minutes)

Windows (PowerShell):

```powershell
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # add ANTHROPIC_API_KEY later; empty = offline mock agent
python manage.py migrate
python manage.py seed_demo      # demo org: admin + 4 devs + 2 weeks of cards + a briefing
python manage.py runserver
```

macOS/Linux: same, but use `python3 -m venv .venv && source .venv/bin/activate` and `cp`.

Open http://127.0.0.1:8000 and log in as `admin@demo.learnloop.dev` / `learnloop-demo-2026`. The members are `ana|ben|dea|edi@demo.learnloop.dev` with the same password. `seed_demo` prints each member's plugin token.

Your own accounts:

```bash
python manage.py create_member you@company.com --name "Your Name" --admin
```

This prints a temp password (changed at first login) and a plugin token. Admins can also create accounts at `/manage/users/new/`.

Run the tests with `python manage.py test core`.

## Install the plugin in Claude Code

1. Make sure Python 3 is on your PATH as `python3` or `python`.
2. In Claude Code:
   ```
   /plugin marketplace add C:/path/to/learnloop      (or the team's git URL)
   /plugin install learnloop@learnloop
   ```
   Claude Code asks for the **server URL** and **token**. You can also set the env vars `LEARNLOOP_URL` and `LEARNLOOP_TOKEN` instead.
3. Start a new session, then click "Test connection" on `/app/setup/`. Or run `python plugin/scripts/ping.py` in a shell that has the env vars set.
4. Ask Claude to build something. When the turn ends you'll see something like:
   ```
   💡 LearnLoop · JWT refresh token rotation  [auth]
   Short-lived access tokens + a refresh token that is replaced on every use…
   Here: src/auth/jwt.ts issues a new refresh token on every /refresh call.
   Read more → http://127.0.0.1:8000/app/cards/41
   ```

For local plugin development: `claude --plugin-dir ./plugin`. Set `LEARNLOOP_DEBUG=1` to log to `~/.claude/plugins/data/…/debug.log`, and `LEARNLOOP_DISABLED=1` to pause the plugin.

### How the plugin stays out of the way

- `collect.py` makes no network calls. It turns each Edit/Write into a small diff, **drops secret files** (`.env*`, keys, certs) and **redacts secrets** (API keys, JWTs, DB URLs, `password = "…"`). It finishes in milliseconds.
- `flush.py` runs once per turn. It sends the batch plus the agent's own summary of the turn (so cards explain *why*), then prints cards through `systemMessage`. That shows the cards to the **user only** and adds nothing to the coding agent's context, so the agent pays nothing.
- If the server is unconfigured, offline or slow, nothing happens. Every script always exits 0, and the server caps each request at about 12 seconds.

## The agents

**Teaching agent** (`POST /api/v1/analyze`) works like this:

1. Cheap gates that use no LLM: account active, under the daily card limit, change not trivial, secrets scrubbed again on the server.
2. A Haiku tool-use loop with these tools: `check_user_knowledge`, `read_full_diff`, `find_docs` (curated official docs), `verify_link`, `create_card`, `skip_concept`.
3. The system prompt sets the rules: skip what this person already knows or what's too basic for their skill level, prefer concepts with business risk (auth, security, data integrity), at most 2 cards, never guess links.
4. Every decision is saved to `AnalyzeLog.trace` and shown at `/manage/activity/`. That's the page to show judges that it really is an agent.

**Manager agent** (`/manage/reports/` or `python manage.py team_report`) works like this:

- Tools: `get_org_overview`, `get_hotspots` (code areas where AI-written code is least understood, with single-point-of-knowledge flags), `get_people_needing_support`, `get_concept_details` (who knows a concept vs. who's still learning it, for pairing ideas), `write_report`.
- Output: a short briefing with risk hotspots, up to 3 concrete actions and wins. Schedule it weekly with cron or Windows Task Scheduler.

**No API key?** Both agents fall back to a deterministic mock that follows the same contract, driven by `core/agent/catalog.py`. UI work and demos run fully offline. Add concepts to the catalog to improve both the mock and the docs links the live agent gets.

## API

`Authorization: Bearer <token>` on every call.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/ping` | Validates the token → `{"user": "Name", "ok": true}` |
| `POST /api/v1/analyze` | `{session_id, changes:[{file, diff}], agent_message?}` → `{cards:[{id, concept, category, summary, why_here, file, diagram, doc_url, url}], outcome, mode}` |
| `GET /app/insights.json` | Member insights (session auth), for dashboard charts |
| `GET /manage/insights.json?days=30` | Org insights (admin session), for dashboard charts |

## Frontend

The dark-first interface remains server-rendered Django; no Node build is required.

- Shared shell and components: `server/core/templates/core/`. Design tokens and responsive styles: `server/core/static/core/app.css`. Navigation, command search (Ctrl/Cmd+K), clipboard feedback, and connection checks: `app.js`.
- Decorative effects live in `motion.css` and `motion.js`: ambient mint glows, cursor lighting, hero depth, viewport entrances, and chart transitions. The Motion toggle remembers your preference; system reduced-motion settings take precedence. Effects pause in hidden tabs, and page content stays usable without JavaScript. No animation library or build step is required.
- Dashboard charts render locally with accessible text values. Mermaid diagrams use the existing CDN dependency, with readable source when previews are unavailable.
- All metrics use existing insights data. The admin mastery chart uses snapshots saved in team briefings, not a continuous daily history.
- POST forms preserve Django CSRF protection and existing action names. The only view changes supply saved reports to the dashboard and render a styled 403 page for non-admin access.
- Standard error templates appear with `DJANGO_DEBUG=0`. Keep serving collected static assets in production as usual.
- Run `python manage.py test core` for backend and frontend integration checks. See `FRONTEND_PLAN.md` for the route map and implementation plan.

## Security checklist

Tokens are stored hashed and shown once. Disabled users lose plugin access immediately. Members only ever see their own cards (every query is filtered by `request.user`). `/manage` is staff-only. Forms use CSRF protection and Django's password validators. The API key lives only in server env vars. Only short snippets are stored on cards, never full diffs. Turn on HTTPS and `DJANGO_DEBUG=0` when deployed.

**Known limits (v1):** rate limiting and the "connected" indicator use a per-process memory cache, which is fine for `runserver` or a single worker. Switch `CACHES` to Redis or the database for multi-worker deploys. Out of scope: YouTube links, quizzes, spaced repetition, SSO, email and multi-tenancy.
