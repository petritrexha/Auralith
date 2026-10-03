"""A small curated catalog of concepts.

Two jobs:
1. `find_docs` tool: gives the live agent trusted official doc links instead of guessed URLs.
2. Mock mode: pattern-based detection so the whole product demos offline, with no API key.

Add entries freely — this is the easiest place for the team to improve quality.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class CatalogEntry:
    slug: str
    name: str
    category: str
    level: str  # "basic" (skip for intermediate users) | "intermediate" | "advanced"
    doc_url: str
    summary: str
    patterns: list[str] = field(default_factory=list)  # any match → candidate (mock mode)
    require: list[str] = field(default_factory=list)  # all must match too (mock mode)
    diagram: str = ""
    keywords: list[str] = field(default_factory=list)
    pitfall: str = ""   # "Watch out" line (standard / deep depth)
    analogy: str = ""   # everyday comparison (when the user wants analogies)

    def matches(self, text: str) -> bool:
        if not any(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in self.patterns):
            return False
        return all(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in self.require)

    def first_match_line(self, text: str) -> int | None:
        for i, line in enumerate(text.splitlines()):
            if any(re.search(p, line, re.IGNORECASE) for p in self.patterns):
                return i
        return None


CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        "flexbox-centering", "Centering with Flexbox", "frontend", "basic",
        "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_flexible_box_layout/Aligning_items_in_a_flex_container",
        "Flexbox turns a container into a flex layout. `justify-content` aligns children on the main axis and `align-items` on the cross axis, so setting both to `center` centers content in both directions without margins or absolute positioning.",
        patterns=[r"display:\s*flex", r"\bflex\b.*\bitems-center\b", r"justify-center"],
        require=[r"(justify-content:\s*center|align-items:\s*center|justify-center|items-center)"],
        diagram="graph LR\n  A[Container display:flex] --> B[justify-content: main axis]\n  A --> C[align-items: cross axis]\n  B --> D[Centered child]\n  C --> D",
        keywords=["css", "flex", "center"],
    ),
    CatalogEntry(
        "css-grid", "CSS Grid layout", "frontend", "intermediate",
        "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout",
        "CSS Grid is a two-dimensional layout system. You define rows and columns on the container (`grid-template-columns`) and children snap into the tracks, which makes dashboards and card layouts much simpler than nested flexboxes.",
        patterns=[r"display:\s*grid", r"grid-template-columns", r"\bgrid-cols-\d"],
        keywords=["css", "grid", "layout"],
    ),
    CatalogEntry(
        "react-usereducer", "React useReducer", "frontend", "intermediate",
        "https://react.dev/reference/react/useReducer",
        "`useReducer` manages state through a reducer function `(state, action) => newState`. Instead of many `useState` calls, every change is described as an action, which keeps complex state transitions in one predictable place.",
        patterns=[r"\buseReducer\s*\("],
        diagram="graph LR\n  UI -->|dispatch action| R[reducer]\n  R -->|new state| S[(state)]\n  S --> UI",
        keywords=["react", "state", "reducer", "hooks"],
    ),
    CatalogEntry(
        "react-useeffect-cleanup", "useEffect cleanup functions", "frontend", "intermediate",
        "https://react.dev/reference/react/useEffect#connecting-to-an-external-system",
        "An effect can return a cleanup function. React runs it before the effect re-runs and when the component unmounts, which is how you unsubscribe listeners, clear timers or abort requests so they don't leak.",
        patterns=[r"useEffect\s*\("], require=[r"return\s*\(\s*\)\s*=>|return\s+function|clearInterval|clearTimeout|removeEventListener|abort\(\)"],
        keywords=["react", "effect", "cleanup", "unmount"],
    ),
    CatalogEntry(
        "react-suspense", "React Suspense", "frontend", "advanced",
        "https://react.dev/reference/react/Suspense",
        "`<Suspense>` shows a fallback while something inside it is still loading (lazy components or suspense-enabled data). It moves loading states out of each component and into one boundary.",
        patterns=[r"<Suspense\b", r"React\.lazy\(|\blazy\(\s*\(\)"],
        keywords=["react", "suspense", "lazy", "loading"],
    ),
    CatalogEntry(
        "react-usememo", "Memoization with useMemo / useCallback", "frontend", "intermediate",
        "https://react.dev/reference/react/useMemo",
        "`useMemo` caches the result of an expensive calculation and `useCallback` caches a function between renders. They only recompute when their dependency array changes, which avoids wasted work and unnecessary child re-renders.",
        patterns=[r"\buseMemo\s*\(", r"\buseCallback\s*\("],
        keywords=["react", "memo", "performance"],
    ),
    CatalogEntry(
        "jwt-refresh-rotation", "JWT refresh token rotation", "auth", "advanced",
        "https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation",
        "Access tokens are short-lived; a long-lived refresh token gets new ones. With rotation, every refresh issues a brand-new refresh token and invalidates the old one, so a stolen refresh token stops working after a single use.",
        patterns=[r"refresh[_-]?token", r"refreshToken"], require=[r"jwt|sign\(|access[_-]?token|accessToken"],
        diagram="sequenceDiagram\n  Client->>API: request + access token (expired)\n  API-->>Client: 401\n  Client->>Auth: refresh token R1\n  Auth-->>Client: new access token + R2 (R1 revoked)",
        keywords=["jwt", "auth", "refresh", "token", "rotation"],
    ),
    CatalogEntry(
        "jwt-auth", "JWT authentication", "auth", "intermediate",
        "https://jwt.io/introduction",
        "A JSON Web Token is a signed string carrying claims (user id, expiry). The server signs it at login and verifies the signature on each request, so it can trust the claims without a session lookup.",
        patterns=[r"\bjwt\.(sign|verify|encode|decode)\b", r"jsonwebtoken", r"\bPyJWT\b|import jwt"],
        keywords=["jwt", "token", "auth"],
    ),
    CatalogEntry(
        "password-hashing", "Password hashing (bcrypt / argon2)", "security", "intermediate",
        "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html",
        "Passwords are never stored as-is. A slow, salted hash like bcrypt or argon2 is stored instead; at login the entered password is hashed and compared. Slowness is the point: it makes brute-forcing leaked hashes expensive.",
        patterns=[r"\bbcrypt\b", r"\bargon2\b", r"make_password|check_password", r"hashpw|gensalt"],
        keywords=["password", "hash", "bcrypt", "security"],
    ),
    CatalogEntry(
        "cors", "CORS (Cross-Origin Resource Sharing)", "api", "intermediate",
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS",
        "Browsers block a page from calling an API on a different origin unless that API answers with `Access-Control-Allow-*` headers. CORS config on the server decides which origins, methods and headers are allowed.",
        patterns=[r"\bcors\s*\(", r"Access-Control-Allow", r"CORS_ALLOWED_ORIGINS|corsheaders|AddCors|UseCors"],
        keywords=["cors", "origin", "headers"],
    ),
    CatalogEntry(
        "rate-limiting", "API rate limiting", "api", "intermediate",
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429",
        "Rate limiting caps how many requests a client may make in a time window and answers `429 Too Many Requests` beyond it. It protects the API from abuse and keeps one noisy client from starving everyone else.",
        patterns=[r"rate[_-]?limit", r"express-rate-limit", r"\bthrottl", r"\b429\b"],
        keywords=["rate limit", "throttle", "429"],
    ),
    CatalogEntry(
        "express-middleware", "Express middleware", "api", "basic",
        "https://expressjs.com/en/guide/using-middleware.html",
        "Middleware are functions `(req, res, next)` that run in order for each request. Each can read or modify the request, end the response, or call `next()` to pass control on — that's how auth, logging and parsing are layered.",
        patterns=[r"\(\s*req\s*,\s*res\s*,\s*next\s*\)", r"app\.use\("],
        keywords=["express", "middleware", "node"],
    ),
    CatalogEntry(
        "promise-all", "Running async work in parallel (Promise.all / gather)", "api", "intermediate",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all",
        "`Promise.all` (or `asyncio.gather` in Python) starts several async operations at once and waits for all of them. Total time becomes the slowest call instead of the sum of all calls; if one fails, the whole thing rejects.",
        patterns=[r"Promise\.all(Settled)?\(", r"asyncio\.gather\(", r"Task\.WhenAll\("],
        keywords=["async", "parallel", "promise"],
    ),
    CatalogEntry(
        "debounce", "Debouncing", "frontend", "intermediate",
        "https://developer.mozilla.org/en-US/docs/Glossary/Debounce",
        "Debouncing delays a function until events stop firing for a set time. A search box that waits 300 ms after the last keystroke before calling the API sends one request instead of one per letter.",
        patterns=[r"\bdebounce\b", r"useDebounce"],
        keywords=["debounce", "input", "performance"],
    ),
    CatalogEntry(
        "django-migrations", "Django migrations", "database", "intermediate",
        "https://docs.djangoproject.com/en/stable/topics/migrations/",
        "Migrations are versioned Python files describing schema changes (add field, create table). `makemigrations` writes them from your models and `migrate` applies them, so every environment's database evolves the same way.",
        patterns=[r"migrations\.(AddField|CreateModel|AlterField|RemoveField|RunPython)", r"class Migration\(migrations\.Migration\)"],
        keywords=["django", "migration", "schema"],
    ),
    CatalogEntry(
        "ef-core-migrations", "EF Core migrations", "database", "intermediate",
        "https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/",
        "Entity Framework Core migrations record model changes as C# classes with `Up` and `Down` methods. `dotnet ef migrations add` creates one and `database update` applies it, keeping the schema in sync with your entities.",
        patterns=[r":\s*Migration\b", r"migrationBuilder\.", r"protected override void Up\("],
        keywords=["ef core", "dotnet", "migration"],
    ),
    CatalogEntry(
        "n-plus-one-queries", "Avoiding N+1 queries (select_related / include)", "database", "advanced",
        "https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-related",
        "An N+1 problem is one query for a list plus one more per row. Eager loading (`select_related`/`prefetch_related` in Django, `.Include()` in EF, `populate` in Mongoose) fetches the related rows up front in one or two queries.",
        patterns=[r"select_related\(", r"prefetch_related\(", r"\.Include\(", r"\.populate\("],
        keywords=["orm", "query", "performance", "n+1"],
    ),
    CatalogEntry(
        "db-transactions", "Database transactions", "database", "intermediate",
        "https://docs.djangoproject.com/en/stable/topics/db/transactions/",
        "A transaction groups several writes so they all succeed or all roll back. If step 3 of 4 fails, steps 1–2 are undone, so the data never ends up half-updated (e.g. money leaving one account but never arriving).",
        patterns=[r"transaction\.atomic", r"BEGIN TRANSACTION|\bCOMMIT\b|ROLLBACK", r"startSession\(\)|withTransaction", r"BeginTransaction"],
        keywords=["transaction", "atomic", "rollback"],
    ),
    CatalogEntry(
        "db-indexes", "Database indexes", "database", "intermediate",
        "https://use-the-index-luke.com/sql/anatomy",
        "An index is a sorted lookup structure on one or more columns. It turns full-table scans into fast lookups for filters and joins, at the cost of extra storage and slightly slower writes.",
        patterns=[r"CREATE (UNIQUE )?INDEX", r"db_index=True", r"models\.Index\(", r"\.index\(\s*\{", r"HasIndex\("],
        keywords=["index", "performance", "sql"],
    ),
    CatalogEntry(
        "schema-validation", "Runtime schema validation (Zod / Pydantic)", "api", "intermediate",
        "https://zod.dev/",
        "Type annotations disappear at runtime, so input from users or APIs is validated against a schema (Zod, Pydantic, Joi). Invalid data is rejected at the edge with a clear error instead of breaking something deep inside.",
        patterns=[r"\bz\.object\(", r"from pydantic import|BaseModel\)", r"Joi\.object\("],
        keywords=["validation", "zod", "pydantic", "schema"],
    ),
    CatalogEntry(
        "docker-multi-stage", "Docker multi-stage builds", "devops", "intermediate",
        "https://docs.docker.com/build/building/multi-stage/",
        "A multi-stage Dockerfile uses one image to build (with compilers and dev deps) and copies only the output into a small runtime image. The final image is smaller, faster to ship and has less attack surface.",
        patterns=[r"^\+?\s*FROM .+ AS \w+"], require=[r"COPY --from="],
        keywords=["docker", "build", "image"],
    ),
    CatalogEntry(
        "github-actions", "CI with GitHub Actions", "devops", "intermediate",
        "https://docs.github.com/en/actions/writing-workflows/quickstart",
        "A GitHub Actions workflow is a YAML file in `.github/workflows` that runs jobs (install, test, deploy) on events like push or pull request, so every change is checked automatically.",
        patterns=[r"runs-on:", r"uses: actions/"],
        keywords=["ci", "github", "workflow"],
    ),
    CatalogEntry(
        "pytest-fixtures", "pytest fixtures", "testing", "intermediate",
        "https://docs.pytest.org/en/stable/how-to/fixtures.html",
        "A fixture is a function marked `@pytest.fixture` that prepares something a test needs (a user, a DB, a client). Tests request it by argument name, and pytest handles setup, sharing and teardown.",
        patterns=[r"@pytest\.fixture"],
        keywords=["pytest", "testing", "fixture"],
    ),
    CatalogEntry(
        "test-mocking", "Mocking in tests", "testing", "intermediate",
        "https://jestjs.io/docs/mock-functions",
        "Mocks replace real dependencies (network, DB, time) with fakes you control. Tests stay fast and deterministic, and you can assert how your code called the dependency.",
        patterns=[r"jest\.mock\(", r"unittest\.mock|@patch\(|mocker\.patch", r"vi\.mock\(", r"new Mock<"],
        keywords=["mock", "testing", "jest"],
    ),
    CatalogEntry(
        "csrf-protection", "CSRF protection", "security", "intermediate",
        "https://owasp.org/www-community/attacks/csrf",
        "Cross-Site Request Forgery tricks a logged-in browser into sending a request the user didn't intend. A per-session CSRF token that a malicious site can't read must accompany every state-changing form, which blocks the forged request.",
        patterns=[r"csrf_token|csrfmiddlewaretoken|csrf_exempt", r"\bcsurf\b|X-CSRF"],
        keywords=["csrf", "security", "forms"],
    ),
    CatalogEntry(
        "websockets", "WebSockets", "api", "intermediate",
        "https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API",
        "A WebSocket keeps one connection open so server and client can push messages to each other at any time — the basis for chats, live dashboards and notifications, without repeated polling.",
        patterns=[r"new WebSocket\(", r"socket\.io", r"\bwebsockets?\b.*(connect|serve)", r"AsyncWebsocketConsumer"],
        keywords=["websocket", "realtime"],
    ),
    CatalogEntry(
        "env-config", "Configuration via environment variables", "devops", "basic",
        "https://12factor.net/config",
        "Settings that change between environments (keys, URLs, flags) are read from environment variables instead of being hard-coded, so the same code runs locally and in production and secrets stay out of git.",
        patterns=[r"process\.env\.", r"os\.environ", r"Environment\.GetEnvironmentVariable"],
        keywords=["env", "config", "12factor"],
    ),
]

# Visual + depth extras per concept: (diagram, pitfall, analogy). A diagram here only fills in when the
# entry above has none. Diagrams stay tiny (≤ 6 nodes, short labels) so they read at a glance.
VISUALS: dict[str, tuple[str, str, str]] = {
    "flexbox-centering": (
        "",
        "Centering needs the container to have a height; a 0-height flex container centers nothing vertically.",
        "Like a shelf that pushes every item to its middle, no matter how many items you put on it.",
    ),
    "css-grid": (
        "graph TD\n  G[Grid container] --> C[Column tracks]\n  G --> R[Row tracks]\n  C --> I[Items snap into cells]\n  R --> I",
        "Fixed pixel tracks break on small screens; prefer fr units and minmax() with auto-fit.",
        "Like a spreadsheet: you define the rows and columns, the content drops into cells.",
    ),
    "react-usereducer": (
        "",
        "Never mutate state inside the reducer; always return a new object, or React won't re-render.",
        "Like a bank teller: you hand over a slip (action) and only the teller updates the balance (state).",
    ),
    "react-useeffect-cleanup": (
        "sequenceDiagram\n  participant C as Component\n  participant E as Effect\n  C->>E: mount: subscribe\n  C->>E: deps change: cleanup, then re-run\n  C->>E: unmount: cleanup",
        "Forgetting cleanup leaks listeners and timers, and in dev Strict Mode effects run twice to expose this.",
        "Like checking out of a hotel: before you leave (unmount) you return the key (unsubscribe).",
    ),
    "react-suspense": (
        "graph LR\n  S[Suspense boundary] -->|still loading| F[Fallback UI]\n  S -->|ready| C[Real content]",
        "One boundary around the whole page hides everything while any part loads; place boundaries close to slow parts.",
        "Like a 'kitchen is preparing your dish' sign that stays up until the plate is ready.",
    ),
    "react-usememo": (
        "graph LR\n  R[Re-render] --> D{Deps changed?}\n  D -->|no| C[Reuse cached value]\n  D -->|yes| X[Recompute]",
        "Memoizing cheap work adds overhead; measure first, and keep the dependency array complete.",
        "Like writing an answer on a sticky note so you don't redo the math unless the numbers change.",
    ),
    "jwt-refresh-rotation": (
        "",
        "If an old refresh token is reused, treat it as theft and revoke the whole token family.",
        "Like a single-use subway ticket: each ride gives you a new one, and the old one stops working.",
    ),
    "jwt-auth": (
        "sequenceDiagram\n  participant U as Client\n  participant A as API\n  U->>A: login\n  A-->>U: signed JWT\n  U->>A: request + Bearer JWT\n  A->>A: verify signature\n  A-->>U: data",
        "A JWT is signed, not encrypted: anyone can read its payload, so never put secrets in it.",
        "Like a festival wristband: staff check it's genuine at each gate without calling the ticket office.",
    ),
    "password-hashing": (
        "graph LR\n  P[Password] --> H[bcrypt or argon2 + salt]\n  H --> D[(Store only the hash)]\n  L[Login attempt] --> H2[Hash again] --> C{Match?}",
        "Fast hashes like SHA-256 are wrong for passwords; use a slow, salted algorithm built for it.",
        "Like a meat grinder: easy to turn steak into mince, impossible to turn it back.",
    ),
    "cors": (
        "sequenceDiagram\n  participant B as Browser\n  participant S as API\n  B->>S: OPTIONS preflight\n  S-->>B: Access-Control-Allow-Origin\n  B->>S: real request\n  S-->>B: response",
        "Access-Control-Allow-Origin: * cannot be combined with cookies; list allowed origins explicitly.",
        "Like a bouncer checking the guest list before letting a visitor from another club inside.",
    ),
    "rate-limiting": (
        "graph LR\n  R[Request] --> K{Under limit?}\n  K -->|yes| H[Handle + count]\n  K -->|no| E[429 Too Many Requests]",
        "In-memory counters only work for one process; use a shared store like Redis when you scale out.",
        "Like a turnstile that only lets so many people through per minute.",
    ),
    "express-middleware": (
        "graph LR\n  Q[Request] --> M1[Logger] --> M2[Auth] --> M3[Body parser] --> H[Route handler]",
        "Forgetting to call next() or send a response leaves the request hanging forever.",
        "Like an airport: check-in, security, then passport control before you reach the gate.",
    ),
    "promise-all": (
        "graph LR\n  S[Start] --> A[Task A]\n  S --> B[Task B]\n  S --> C[Task C]\n  A --> J[All done]\n  B --> J\n  C --> J",
        "Promise.all rejects as soon as one task fails; use Promise.allSettled when partial results are fine.",
        "Like ordering coffee, a sandwich and juice at once instead of waiting for each one in turn.",
    ),
    "debounce": (
        "sequenceDiagram\n  participant U as User\n  participant D as Debounce 300ms\n  participant A as API\n  U->>D: keystroke\n  U->>D: keystroke (timer resets)\n  D->>A: one call after the pause",
        "Create the debounced function once (useMemo/useRef); recreating it every render resets the timer.",
        "Like an elevator door that waits until people stop walking in before it closes.",
    ),
    "django-migrations": (
        "graph LR\n  M[models.py change] --> MK[makemigrations] --> F[Migration file in git] --> MG[migrate] --> DB[(Database schema)]",
        "Never edit a migration that already ran in production; add a new one instead.",
        "Like version control for your database layout.",
    ),
    "ef-core-migrations": (
        "graph LR\n  M[Entity change] --> A[dotnet ef migrations add] --> F[Migration class] --> U[database update] --> DB[(Schema)]",
        "Review the generated Up() method: a rename can be scaffolded as drop + add, which loses data.",
        "Like a recipe card for turning yesterday's database into today's.",
    ),
    "n-plus-one-queries": (
        "graph LR\n  L[Load 50 orders] -->|N+1| Q1[1 query + 50 queries]\n  L -->|eager load| Q2[2 queries total]",
        "It hides in templates and serializers that touch a relation inside a loop; watch query counts in tests.",
        "Like making 50 trips to the shop for 50 items instead of one trip with a list.",
    ),
    "db-transactions": (
        "graph LR\n  B[BEGIN] --> S1[Debit A] --> S2[Credit B] --> C{All ok?}\n  C -->|yes| CM[COMMIT]\n  C -->|no| RB[ROLLBACK]",
        "Don't call slow external APIs inside a transaction: it holds locks open for the whole call.",
        "Like a bank transfer: either both accounts change or neither does.",
    ),
    "db-indexes": (
        "graph LR\n  Q[WHERE email = ?] --> I{Index on email?}\n  I -->|yes| F[Jump straight to row]\n  I -->|no| S[Scan every row]",
        "Every index slows writes and uses space; index the columns you filter and sort on, not everything.",
        "Like the index at the back of a book instead of reading every page.",
    ),
    "schema-validation": (
        "graph LR\n  I[Untrusted input] --> V{Schema check}\n  V -->|valid| T[Typed data to your code]\n  V -->|invalid| E[400 with field errors]",
        "Validate at the boundary (request, env, external API), then trust the typed result inside.",
        "Like airport security: check everything once at the entrance so the inside can stay relaxed.",
    ),
    "docker-multi-stage": (
        "graph LR\n  B[Build stage: SDK + deps] -->|copy only output| R[Runtime stage: slim image]\n  R --> I[Small, safer image]",
        "Copying the whole build stage back defeats the purpose; copy only the built artifacts.",
        "Like cooking in a full kitchen but serving only the plate, not the pots.",
    ),
    "github-actions": (
        "graph LR\n  P[Push or PR] --> W[Workflow] --> J1[Install] --> J2[Test] --> J3[Deploy if main]",
        "Secrets aren't available to PRs from forks; don't build workflows that assume they are.",
        "Like a robot colleague who runs the same checklist on every change.",
    ),
    "pytest-fixtures": (
        "graph LR\n  F[Fixture: setup] --> T1[test_a]\n  F --> T2[test_b]\n  T1 --> TD[Teardown after yield]\n  T2 --> TD",
        "Broad-scoped fixtures (module/session) share state between tests; keep mutable fixtures function-scoped.",
        "Like a stage crew setting the scene before each act and clearing it after.",
    ),
    "test-mocking": (
        "graph LR\n  T[Test] --> C[Your code]\n  C -->|would call| R[Real API]\n  C -->|calls instead| M[Mock with canned answer]",
        "Patch where the name is looked up, not where it's defined, or the mock never takes effect.",
        "Like a flight simulator: real controls, fake sky.",
    ),
    "csrf-protection": (
        "sequenceDiagram\n  participant B as Browser\n  participant S as Server\n  S-->>B: page + secret CSRF token\n  B->>S: POST form + token + cookie\n  S->>S: token matches session?",
        "Exempting views from CSRF (csrf_exempt) is only safe when they don't rely on cookies for auth.",
        "Like a ticket stub: the cookie proves who you are, the stub proves you came from the real form.",
    ),
    "websockets": (
        "sequenceDiagram\n  participant C as Client\n  participant S as Server\n  C->>S: HTTP upgrade\n  S-->>C: 101 Switching Protocols\n  S-->>C: push message\n  C->>S: send message",
        "Connections drop: build reconnect with backoff, and re-sync state after reconnecting.",
        "Like a phone call that stays open, instead of sending a new letter for every update.",
    ),
    "env-config": (
        "graph LR\n  E[.env or host settings] --> P[Process environment] --> A[App reads config at start]\n  G[git] -.never.- E",
        "Commit a .env.example with dummy values, never the real .env.",
        "Like keeping the house keys out of the house blueprints.",
    ),
}

for _entry in CATALOG:
    _diagram, _pitfall, _analogy = VISUALS.get(_entry.slug, ("", "", ""))
    _entry.diagram = _entry.diagram or _diagram
    _entry.pitfall = _entry.pitfall or _pitfall
    _entry.analogy = _entry.analogy or _analogy

BY_SLUG = {e.slug: e for e in CATALOG}


def search(query: str, limit: int = 3) -> list[CatalogEntry]:
    """Very small keyword search used by the `find_docs` tool."""
    q = query.lower()
    words = [w for w in re.split(r"[^a-z0-9+#]+", q) if len(w) > 1]
    scored = []
    for e in CATALOG:
        hay = " ".join([e.slug, e.name.lower(), " ".join(e.keywords)])
        score = sum(2 if w in e.slug else 1 for w in words if w in hay)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in scored[:limit]]


def detect(text: str) -> list[CatalogEntry]:
    return [e for e in CATALOG if e.matches(text)]
