"""The skill checklist: area → general topic → niche skill, ticked by members as "I know this".

A ticked item is stored as a normal known Concept (slug = item slug) and also *covers* every concept
the agent might surface whose slug matches one of its patterns. Ticking a general topic covers all of its
niche skills too; ticking one niche skill covers only that skill. E.g. ticking "useReducer for complex state"
blocks cards for `react-usereducer` and `usereducer-for-complex-state`, but still allows `useeffect-cleanup`.

Patterns are regexes matched against concept slugs at a word boundary (start of slug or after a hyphen).
Keep them specific: an over-broad pattern silently hides cards. This is a starting map, not every skill
there is — anything outside it is still tracked from real work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.models import CHECKLIST_SLUG_PREFIX


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    patterns: tuple[str, ...]
    children: tuple["Topic", ...] = ()
    parent: str = ""  # slug of the general topic, for niche skills

    def covers(self, slug: str) -> bool:
        if slug == self.slug or any(re.search(r"(?:^|-)(?:" + p + ")", slug) for p in self.patterns):
            return True
        return any(child.covers(slug) for child in self.children)


@dataclass(frozen=True)
class Sector:
    key: str
    name: str
    category: str  # Concept.Category used when an item is stored
    blurb: str
    topics: tuple[Topic, ...] = field(default=())

    @property
    def skills(self) -> list[Topic]:
        return [n for t in self.topics for n in t.children]


def _topic(key: str, name: str, patterns: str, *niche: tuple[str, str, str]) -> Topic:
    """Compact definition: `patterns` is one regex alternation; each niche skill is (key, name, patterns)."""
    slug = CHECKLIST_SLUG_PREFIX + key
    children = tuple(Topic(f"{slug}-{k}", n, (p,), parent=slug) for k, n, p in niche)
    return Topic(slug, name, (patterns,) if patterns else (), children)


T = _topic

SECTORS: tuple[Sector, ...] = (
    Sector("frontend", "Frontend", "frontend", "What runs in the browser.", (
        T("html-css", "HTML & CSS foundations", r"semantic-html",
          ("semantic", "Semantic HTML (header, main, nav, article)", r"semantic-html|html5-semantic"),
          ("specificity", "Selector specificity & the cascade", r"specificity|css-cascade"),
          ("box-model", "Box model, margins & box-sizing", r"box-model|box-sizing|margin-collaps"),
          ("variables", "CSS custom properties (variables)", r"css-variable|custom-propert"),
          ("pseudo", "Pseudo-classes & pseudo-elements", r"pseudo-(class|element)"),
          ("animations", "Transitions & keyframe animations", r"css-(animation|transition)|keyframe")),
        T("css-layout", "CSS layout", r"flex-layout|css-layout",
          ("flexbox", "Flexbox alignment & wrapping", r"flexbox|flex-wrap|justify-content|align-items"),
          ("grid", "CSS Grid templates & areas", r"css-grid|grid-layout|grid-template"),
          ("positioning", "Positioning, sticky & z-index stacking", r"position-(sticky|absolute|fixed)|sticky|z-index|stacking-context"),
          ("responsive", "Responsive design & media queries", r"responsive|media-quer|mobile-first"),
          ("container-queries", "Container queries", r"container-quer"),
          ("tailwind", "Tailwind utility classes", r"tailwind")),
        T("js-core", "JavaScript language core", r"javascript-(core|basics)",
          ("closures", "Closures & scope", r"closure|lexical-scope"),
          ("this", "`this`, bind & arrow functions", r"this-binding|arrow-function"),
          ("destructuring", "Destructuring, spread & rest", r"destructur|spread-operator|rest-param"),
          ("array-methods", "map / filter / reduce", r"array-(map|filter|reduce|method)|reduce\b|single-pass-reduce"),
          ("optional-chaining", "Optional chaining & nullish coalescing", r"optional-chaining|nullish"),
          ("modules", "ES modules & dynamic import", r"es-module|esm\b|dynamic-import"),
          ("events", "DOM events, bubbling & delegation", r"event-(delegation|bubbling|propagation)|dom-event")),
        T("react-core", "React fundamentals", r"react-(component|props|jsx|basics)",
          ("jsx-keys", "JSX & list keys", r"jsx|react-key|list-key"),
          ("props", "Props, children & composition", r"props\b|prop-drilling|component-composition"),
          ("controlled", "Controlled vs uncontrolled inputs", r"controlled-(input|component|form)|uncontrolled"),
          ("conditional", "Conditional rendering", r"conditional-render"),
          ("lifting-state", "Lifting state up", r"lifting-state"),
          ("error-boundaries", "Error boundaries", r"error-boundar")),
        T("react-hooks", "React hooks", r"react-hook|react-use",
          ("usestate", "useState & functional updates", r"usestate|functional-update|state-update"),
          ("useeffect", "useEffect, dependencies & cleanup", r"useeffect|effect-cleanup|dependency-array"),
          ("usereducer", "useReducer for complex state", r"usereducer|reducer-pattern"),
          ("usememo", "useMemo & useCallback", r"usememo|usecallback"),
          ("useref", "useRef for DOM & mutable values", r"useref"),
          ("usecontext", "useContext", r"usecontext"),
          ("custom", "Writing custom hooks", r"custom-hook")),
        T("state-management", "App state management", r"state-management",
          ("context", "Context API for shared state", r"react-context|context-api|context-provider"),
          ("redux", "Redux Toolkit (slices, thunks)", r"redux"),
          ("stores", "Zustand / Jotai stores", r"zustand|jotai"),
          ("server-state", "Server state (React Query, SWR)", r"react-query|tanstack-query|swr\b|server-state"),
          ("url-state", "State in the URL (search params)", r"url-state|search-param|query-param"),
          ("optimistic", "Optimistic UI updates", r"optimistic-(update|ui)")),
        T("nextjs", "Next.js & rendering", r"next-?js",
          ("app-router", "App Router: layouts & routes", r"app-router|nextjs-layout|file-based-rout"),
          ("server-components", "Server vs client components", r"server-component|client-component|use-client"),
          ("hydration", "Hydration & mismatches", r"hydration"),
          ("ssr-ssg", "SSR, SSG & ISR", r"ssr\b|ssg\b|isr\b|server-side-render|static-generation|incremental-static"),
          ("server-actions", "Server actions & route handlers", r"server-action|route-handler"),
          ("images", "next/image & font optimization", r"next-image|image-optimi")),
        T("typescript", "TypeScript", r"typescript",
          ("types-interfaces", "Interfaces vs type aliases", r"interface-vs-type|type-alias|ts-interface"),
          ("generics", "Generics", r"generics?\b|ts-generic"),
          ("narrowing", "Union types & narrowing", r"union-type|narrowing|type-guard|discriminated-union"),
          ("utility-types", "Utility types (Partial, Pick, Record)", r"utility-type|partial-type|pick-type|record-type"),
          ("literals", "`as const` & literal types", r"as-const|literal-type"),
          ("strict-null", "Strict null checks & non-null assertions", r"strict-null|non-null-assert")),
        T("web-performance", "Frontend performance", r"web-performance|frontend-performance",
          ("rerenders", "React.memo & avoiding re-renders", r"react-memo|re-render|memoiz"),
          ("debounce", "Debounce & throttle", r"debounc|throttl"),
          ("code-splitting", "Code splitting & lazy loading", r"code-split|lazy-load|react-lazy|react-suspense"),
          ("virtualization", "List virtualization", r"virtuali[sz]|windowing"),
          ("web-vitals", "Core Web Vitals (LCP, CLS, INP)", r"web-vital|lcp\b|cls\b|inp\b"),
          ("images", "Responsive & lazy images", r"image-lazy|responsive-image|webp")),
        T("accessibility", "Accessibility", r"a11y|accessib",
          ("aria", "ARIA roles & labels", r"aria\b|aria-"),
          ("focus", "Focus management & keyboard navigation", r"focus-(trap|management|visible)|keyboard-nav"),
          ("contrast", "Color contrast", r"color-contrast|contrast-ratio"),
          ("screen-readers", "Screen-reader text & live regions", r"screen-reader|sr-only|live-region"),
          ("forms", "Accessible forms & labels", r"form-label|accessible-form")),
    )),
    Sector("backend", "Backend", "api", "Servers, APIs and the logic behind them.", (
        T("http-api", "HTTP & REST APIs", r"rest-?api|restful|api-design",
          ("methods", "HTTP methods & idempotency", r"http-(method|verb)|idempoten"),
          ("status-codes", "Status codes (2xx / 4xx / 5xx)", r"http-status|status-code"),
          ("headers", "Headers & content negotiation", r"http-header|content-type|content-negotiation"),
          ("pagination", "Pagination (offset & cursor)", r"paginat|cursor-based"),
          ("versioning", "API versioning", r"api-version"),
          ("graphql", "GraphQL queries & resolvers", r"graphql|resolver"),
          ("openapi", "OpenAPI / Swagger docs", r"openapi|swagger")),
        T("frameworks", "Server frameworks", r"web-framework",
          ("express", "Express routing & middleware", r"express"),
          ("django", "Django views, URLs & forms", r"django-(view|url|template|form)"),
          ("fastapi", "FastAPI routers & dependencies", r"fastapi|dependency-inject"),
          ("middleware", "Middleware pipelines", r"middleware|request-pipeline"),
          ("aspnet", "ASP.NET Core controllers & DI", r"asp-?net|dotnet|minimal-api"),
          ("spring", "Spring Boot", r"spring")),
        T("async", "Async & concurrency", r"concurren",
          ("promises", "Promises & async/await", r"promise|async-await"),
          ("parallel", "Parallel work (Promise.all, gather)", r"promise-all|asyncio-gather|parallel-"),
          ("event-loop", "The event loop", r"event-loop"),
          ("asyncio", "Python asyncio", r"asyncio"),
          ("race-conditions", "Race conditions & mutexes", r"race-condition|mutex"),
          ("streams", "Streams & backpressure", r"streams?\b|backpressure")),
        T("validation", "Validation & error handling", r"validation\b",
          ("schemas", "Schema validation (Zod, Pydantic)", r"schema-validation|zod\b|pydantic|request-validation|input-validation"),
          ("errors", "Error handling & custom errors", r"error-handl|custom-error|exception-handl"),
          ("retries", "Retries & exponential backoff", r"retr(y|ies)|backoff"),
          ("idempotency-keys", "Idempotency keys", r"idempotency-key"),
          ("timeouts", "Timeouts & circuit breakers", r"timeout|circuit-breaker")),
        T("caching", "Caching", r"cach(e|ing)",
          ("redis", "Redis as a cache", r"redis"),
          ("http-cache", "HTTP caching (Cache-Control, ETag)", r"cache-control|etag|http-cach"),
          ("invalidation", "Cache invalidation & TTLs", r"cache-invalidat|ttl\b"),
          ("in-memory", "In-memory / LRU caches", r"lru-cache|in-memory-cache"),
          ("cdn", "CDN edge caching", r"cdn\b|edge-cach")),
        T("background", "Background work", r"background-(job|task)",
          ("queues", "Job queues (Celery, BullMQ, Sidekiq)", r"job-queue|task-queue|celery|bullmq|sidekiq"),
          ("cron", "Scheduled jobs (cron)", r"cron\b|scheduled-(job|task)"),
          ("brokers", "Message brokers (RabbitMQ, Kafka, pub/sub)", r"message-(queue|broker)|rabbitmq|kafka|pub-sub"),
          ("webhooks", "Webhooks: sending & verifying", r"webhook"),
          ("workers", "Worker processes", r"worker-process|background-worker")),
        T("realtime", "Realtime", r"real-?time",
          ("websockets", "WebSockets", r"websocket|socket-io"),
          ("sse", "Server-sent events", r"server-sent|sse\b"),
          ("polling", "Polling & long polling", r"polling|long-poll"),
          ("presence", "Presence, rooms & channels", r"presence|chat-room")),
        T("rate-limiting", "Rate limiting", r"rate-limit",
          ("windows", "Fixed & sliding window counters", r"fixed-window|sliding-window"),
          ("token-bucket", "Token bucket / leaky bucket", r"token-bucket|leaky-bucket"),
          ("quotas", "Per-user limits & quotas", r"per-user-limit|api-quota")),
    )),
    Sector("data", "Databases", "database", "Storing and querying data safely.", (
        T("sql", "SQL", r"sql-(quer|basics)",
          ("joins", "JOINs (inner, left, outer)", r"joins?\b|inner-join|left-join"),
          ("group-by", "GROUP BY & aggregates", r"group-by|sql-aggregat|aggregate-function"),
          ("subqueries", "Subqueries & CTEs", r"subquer|cte\b|common-table"),
          ("window-functions", "Window functions", r"window-function"),
          ("upserts", "Upserts (ON CONFLICT)", r"upsert|on-conflict"),
          ("parameters", "Parameterized queries", r"parameteri[sz]ed-quer|prepared-statement")),
        T("modeling", "Data modeling", r"data-model|schema-design",
          ("normalization", "Normalization", r"normali[sz]ation"),
          ("relations", "One-to-many, many-to-many & foreign keys", r"one-to-many|many-to-many|foreign-key"),
          ("constraints", "Constraints (unique, check, not null)", r"unique-constraint|check-constraint|db-constraint"),
          ("soft-delete", "Soft deletes", r"soft-delete"),
          ("keys", "UUID vs auto-increment keys", r"uuid|primary-key"),
          ("json-columns", "JSON columns", r"jsonb|json-column|jsonfield")),
        T("orm", "ORMs", r"orm\b",
          ("django-orm", "Django ORM querysets", r"django-orm|queryset"),
          ("prisma", "Prisma", r"prisma"),
          ("sqlalchemy", "SQLAlchemy sessions", r"sqlalchemy"),
          ("ef-core", "Entity Framework Core", r"entity-framework|ef-core"),
          ("eager-loading", "Eager loading (select_related, include)", r"select-related|prefetch|eager-load"),
          ("raw-sql", "Dropping to raw SQL safely", r"raw-sql|raw-quer")),
        T("migrations", "Migrations", r"migration",
          ("data-migrations", "Data migrations & backfills", r"data-migration|backfill"),
          ("zero-downtime", "Zero-downtime schema changes", r"zero-downtime|expand-contract"),
          ("rollback", "Rolling back migrations", r"migration-rollback|down-migration")),
        T("db-performance", "Query performance", r"query-(performance|optimi)",
          ("indexes", "Indexes (B-tree, composite)", r"db-index|database-index|indexing|composite-index"),
          ("n-plus-one", "N+1 queries", r"n-plus-one|n1-quer"),
          ("explain", "EXPLAIN & query plans", r"explain-analyze|query-plan"),
          ("pooling", "Connection pooling", r"connection-pool"),
          ("bulk", "Bulk inserts & batching", r"bulk-(insert|create|update)|batch-insert")),
        T("transactions", "Transactions & integrity", r"transactions?\b|db-transaction|database-transaction",
          ("atomic", "Atomic blocks & rollbacks", r"atomic"),
          ("isolation", "Isolation levels", r"isolation-level"),
          ("row-locks", "Row locks (SELECT … FOR UPDATE)", r"select-for-update|row-lock|pessimistic-lock"),
          ("optimistic-locking", "Optimistic locking (version columns)", r"optimistic-lock|optimistic-concurren"),
          ("deadlocks", "Deadlocks", r"deadlock")),
        T("nosql", "NoSQL & vector stores", r"nosql",
          ("mongodb", "MongoDB documents & aggregation", r"mongo"),
          ("firestore", "Firestore / Firebase", r"firestore|firebase"),
          ("dynamodb", "DynamoDB keys & indexes", r"dynamo"),
          ("redis-structures", "Redis data structures", r"redis-(data|sorted|hash|stream)"),
          ("vectors", "Vector search & embeddings", r"vector-(db|database|search)|pgvector")),
    )),
    Sector("security", "Auth & security", "security", "Who can do what, and keeping it safe.", (
        T("sessions-cookies", "Sessions & cookies", r"session-(auth|cookie|management)",
          ("cookie-flags", "HttpOnly, Secure & SameSite", r"httponly|samesite|secure-cookie|cookie-flag"),
          ("session-store", "Server-side session storage", r"session-store"),
          ("expiry", "Session expiry & remember-me", r"remember-me|session-expir"),
          ("logout", "Logout & session invalidation", r"logout|session-invalidat")),
        T("jwt", "Tokens & JWT", r"jwt|bearer-token",
          ("structure", "JWT structure & signing", r"jwt-(structure|sign|auth)"),
          ("refresh", "Access + refresh tokens & rotation", r"refresh-token|jwt-refresh|token-rotation"),
          ("storage", "Where to store tokens", r"token-storage"),
          ("api-keys", "API keys & hashing them", r"api-key")),
        T("oauth", "OAuth & SSO", r"oauth|sso\b",
          ("pkce", "Authorization code + PKCE", r"pkce|authorization-code"),
          ("oidc", "OpenID Connect & ID tokens", r"oidc|openid|id-token"),
          ("social", "Social login (Google, GitHub)", r"social-login|google-login|github-oauth"),
          ("saml", "SAML", r"saml"),
          ("libraries", "Auth libraries (NextAuth, Clerk, Auth0)", r"next-?auth|clerk|auth0|supabase-auth")),
        T("passwords", "Passwords & MFA", r"password-(policy|auth)",
          ("hashing", "Password hashing (bcrypt, argon2)", r"password-hash|bcrypt|argon|pbkdf2"),
          ("reset", "Password reset flows", r"password-reset|reset-token"),
          ("mfa", "MFA & TOTP", r"mfa\b|totp|two-factor|2fa"),
          ("passkeys", "Passkeys & WebAuthn", r"passkey|webauthn")),
        T("web-security", "Web vulnerabilities", r"web-security|owasp",
          ("xss", "XSS & output escaping", r"xss|output-escap|sanitiz"),
          ("csrf", "CSRF tokens", r"csrf"),
          ("cors", "CORS", r"cors\b"),
          ("injection", "SQL & command injection", r"sql-injection|command-injection|injection-attack"),
          ("csp", "Content Security Policy", r"content-security-policy|csp\b"),
          ("ssrf", "SSRF & open redirects", r"ssrf|open-redirect")),
        T("authorization", "Authorization", r"authori[sz]ation|access-control",
          ("rbac", "Role-based access (RBAC)", r"rbac|role-based"),
          ("object-level", "Object-level checks (IDOR)", r"idor|object-level|ownership-check"),
          ("policies", "Permission classes & policies", r"permissions?\b|policy-based"),
          ("multi-tenant", "Multi-tenancy & row-level security", r"multi-tenan|row-level-security|rls\b")),
        T("secrets", "Secrets & encryption", r"secrets?-management",
          ("env", "Environment variables & .env files", r"env-config|environment-variable|dotenv"),
          ("managers", "Secret managers (Vault, AWS SM)", r"vault|secret-manager"),
          ("rotation", "Key rotation", r"key-rotation|secret-rotation"),
          ("encryption", "Encryption at rest & in transit", r"encrypt")),
    )),
    Sector("hosting", "Hosting & DevOps", "devops", "Shipping it and keeping it running.", (
        T("docker", "Containers", r"docker|container",
          ("dockerfile", "Dockerfile layers & build cache", r"dockerfile|docker-layer"),
          ("multi-stage", "Multi-stage builds", r"multi-stage"),
          ("compose", "Docker Compose", r"docker-compose|compose\b"),
          ("volumes", "Volumes & networks", r"docker-(volume|network)"),
          ("kubernetes", "Kubernetes basics (pods, deployments)", r"kubernetes|k8s|helm|pods?\b")),
        T("ci-cd", "CI/CD", r"ci-cd|continuous-(integration|deploy)",
          ("github-actions", "GitHub Actions workflows", r"github-actions|workflow-yaml"),
          ("ci-cache", "CI caching & build matrices", r"ci-cache|build-matrix"),
          ("previews", "Preview deployments", r"preview-deploy"),
          ("releases", "Releases, tags & semver", r"semver|release-"),
          ("gitlab", "GitLab CI", r"gitlab-ci")),
        T("cloud", "Cloud platforms", r"cloud-platform",
          ("vercel", "Vercel / Netlify deploys", r"vercel|netlify"),
          ("aws", "AWS core (EC2, S3, IAM)", r"aws\b|s3\b|ec2|iam\b"),
          ("serverless", "Serverless & edge functions", r"serverless|lambda|edge-function"),
          ("paas", "PaaS (Render, Railway, Fly, Heroku)", r"heroku|render-com|railway|fly-io|paas"),
          ("azure-gcp", "Azure / Google Cloud", r"azure|gcp\b|google-cloud"),
          ("iac", "Infrastructure as code (Terraform)", r"terraform|infrastructure-as-code|iac\b|pulumi")),
        T("networking", "Networking & domains", r"networking",
          ("dns", "DNS records (A, CNAME)", r"dns\b|cname|dns-record"),
          ("https", "HTTPS & TLS certificates", r"https\b|tls\b|ssl\b|certificate|lets-encrypt"),
          ("reverse-proxy", "Reverse proxies (Nginx, Caddy)", r"nginx|reverse-proxy|caddy"),
          ("load-balancing", "Load balancing", r"load-balanc"),
          ("ports", "Ports & firewalls", r"port-binding|firewall")),
        T("observability", "Observability", r"observab|monitor",
          ("logging", "Structured logging", r"logging|structured-log"),
          ("error-tracking", "Error tracking (Sentry)", r"sentry|error-tracking"),
          ("metrics", "Metrics & dashboards", r"metrics|prometheus|grafana"),
          ("tracing", "Distributed tracing (OpenTelemetry)", r"tracing|opentelemetry|telemetry"),
          ("health", "Health checks & uptime", r"health-check|uptime")),
        T("reliability", "Scaling & reliability", r"scal(ing|ability)",
          ("horizontal", "Horizontal scaling & stateless apps", r"horizontal-scal|stateless"),
          ("autoscaling", "Autoscaling", r"autoscal"),
          ("backups", "Backups & restore", r"backup"),
          ("feature-flags", "Feature flags & gradual rollouts", r"feature-flag|rollout|canary")),
    )),
    Sector("quality", "Testing & workflow", "testing", "Proving it works and working as a team.", (
        T("unit-tests", "Unit testing", r"unit-test|test-driven|tdd\b",
          ("pytest", "pytest", r"pytest"),
          ("jest", "Jest / Vitest", r"jest\b|vitest"),
          ("structure", "Assertions & test structure (AAA)", r"assertion|arrange-act"),
          ("parametrize", "Parametrized tests", r"parametri[sz]"),
          ("coverage", "Coverage", r"test-coverage|code-coverage")),
        T("mocking", "Test doubles", r"test-double",
          ("mocks", "Mocks & spies", r"mock|spy\b|spies"),
          ("fixtures", "Fixtures & factories", r"fixture|factory-boy|test-factor"),
          ("http-stubs", "Stubbing HTTP (MSW, responses)", r"msw\b|http-mock|stub"),
          ("time", "Freezing time & fake timers", r"freeze-time|freezegun|fake-timer")),
        T("integration-tests", "Integration & end-to-end tests", r"integration-test",
          ("api-tests", "API tests with a test client", r"api-test"),
          ("e2e", "Playwright / Cypress E2E", r"e2e|end-to-end|playwright|cypress"),
          ("component", "Component tests (Testing Library)", r"testing-library|component-test"),
          ("test-db", "Test databases & isolation", r"test-database|test-isolation")),
        T("git", "Git", r"git\b|git-workflow",
          ("branching", "Branching & merging", r"git-(branch|merge)|branching"),
          ("rebase", "Rebase & rewriting history", r"rebase"),
          ("conflicts", "Merge conflicts", r"merge-conflict"),
          ("pull-requests", "Pull requests & code review", r"pull-request|code-review"),
          ("hooks", ".gitignore & pre-commit hooks", r"gitignore|git-hook|pre-commit")),
        T("code-quality", "Code quality", r"code-quality",
          ("lint", "Linting (ESLint, Ruff)", r"lint|eslint|ruff\b"),
          ("format", "Formatting (Prettier, Black)", r"prettier|code-format|black-format"),
          ("type-check", "Type checking in CI (mypy, tsc)", r"mypy|type-check"),
          ("refactoring", "Refactoring patterns", r"refactor"),
          ("design-patterns", "SOLID & design patterns", r"solid-principle|design-pattern|dependency-injection")),
    )),
    Sector("ai", "AI & LLM apps", "other", "Building on top of language models.", (
        T("llm-apis", "LLM APIs", r"llm-api|claude-api|openai-api|anthropic-api",
          ("prompts", "Prompt & system prompt design", r"prompt-(design|engineering|template)|system-prompt|prompting"),
          ("tool-use", "Tool use / function calling", r"tool-use|function-calling"),
          ("streaming", "Streaming responses", r"streaming-response|stream-llm|llm-stream"),
          ("tokens", "Tokens, context windows & cost", r"token-count|context-window|prompt-caching"),
          ("structured", "Structured output (JSON mode)", r"structured-output|json-mode")),
        T("ai-systems", "AI systems", r"ai-system",
          ("rag", "RAG & retrieval", r"rag\b|retrieval-augment"),
          ("embeddings", "Embeddings & similarity search", r"embedding|cosine-similar"),
          ("agents", "Agent loops", r"agent-loop|ai-agent|agentic"),
          ("evals", "Evals & guardrails", r"llm-eval|evals?\b|guardrail")),
    )),
)

TOPICS: dict[str, Topic] = {}
SECTOR_OF: dict[str, Sector] = {}
for _sector in SECTORS:
    for _general in _sector.topics:
        for _item in (_general, *_general.children):
            TOPICS[_item.slug] = _item
            SECTOR_OF[_item.slug] = _sector

TOTAL_SKILLS = sum(len(s.skills) for s in SECTORS)


def covering_topics(slug: str, known_topic_slugs) -> list[Topic]:
    """Which of the user's ticked items cover this concept slug."""
    return [TOPICS[t] for t in known_topic_slugs if t in TOPICS and TOPICS[t].covers(slug)]


def known_skill_count(known_topic_slugs) -> int:
    """Niche skills known, directly or because their whole general topic is ticked."""
    ticked = set(known_topic_slugs)
    return sum(1 for s in SECTORS for n in s.skills if n.slug in ticked or n.parent in ticked)


# ---------------------------------------------------------------------------
# Motivation: levels and encouraging copy (dashboard + concepts page + tick toasts)
# ---------------------------------------------------------------------------
LEVELS = (  # (skills needed, name, message)
    (0, "Getting started", "Tick the skills you already have. Every tick means fewer cards about things you know."),
    (5, "Explorer", "Nice start! Each tick teaches LearnLoop what to skip for you."),
    (15, "Builder", "You're building a real picture of your skills. Keep going!"),
    (40, "Practitioner", "Impressive range. Your cards are getting sharper with every tick."),
    (80, "Expert", "Serious depth. LearnLoop now talks to you like a pro."),
    (150, "Architect", "Architect-level map. Only genuinely new things will reach you now."),
)


def progress(known_topic_slugs) -> dict:
    count = known_skill_count(known_topic_slugs)
    idx = max(i for i, (need, _, _) in enumerate(LEVELS) if count >= need)
    _, level, message = LEVELS[idx]
    nxt = LEVELS[idx + 1] if idx + 1 < len(LEVELS) else None
    return {
        "count": count,
        "total": TOTAL_SKILLS,
        "percent": round(100 * count / TOTAL_SKILLS),
        "level": level,
        "level_index": idx,
        "message": message,
        "next_level": nxt[1] if nxt else "",
        "to_next": (nxt[0] - count) if nxt else 0,
        "next_percent": round(100 * (count - LEVELS[idx][0]) / (nxt[0] - LEVELS[idx][0])) if nxt else 100,
        "ladder": [{"name": name, "need": need, "reached": count >= need} for need, name, _ in LEVELS[1:]],
    }
