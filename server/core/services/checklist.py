"""The skill checklist: broad topics a member can tick as "I know this".

A ticked topic is stored as a normal known Concept (slug = topic slug), and it also *covers* every
narrower concept whose slug matches one of its patterns, e.g. ticking "React hooks" blocks cards for
`react-usereducer`, `usememo-dependency-arrays`, `useeffect-cleanup`, ...

Patterns are matched against concept slugs at a word boundary (start of slug or after a hyphen).
Keep them specific: an over-broad pattern silently hides cards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    patterns: tuple[str, ...]

    def covers(self, slug: str) -> bool:
        return slug == self.slug or any(re.search(r"(?:^|-)(?:" + p + ")", slug) for p in self.patterns)


@dataclass(frozen=True)
class Sector:
    key: str
    name: str
    category: str  # Concept.Category used when a topic is stored
    blurb: str
    topics: tuple[Topic, ...]


SECTORS: tuple[Sector, ...] = (
    Sector("frontend", "Frontend", "frontend", "What runs in the browser.", (
        Topic("stack-css-layout", "CSS layout (Flexbox & Grid)", (r"flexbox", r"css-grid", r"grid-layout", r"flex-layout")),
        Topic("stack-responsive-design", "Responsive design & media queries", (r"responsive", r"media-quer", r"mobile-first")),
        Topic("stack-react-hooks", "React hooks (useState, useEffect, useReducer…)", (r"react-hook", r"react-use", r"use(state|effect|reducer|memo|callback|ref|context|layouteffect)\b", r"custom-hook")),
        Topic("stack-state-management", "State management (Context, Redux, Zustand)", (r"redux", r"zustand", r"react-context", r"context-api", r"state-management")),
        Topic("stack-ssr-hydration", "SSR, Next.js & hydration", (r"next-?js", r"hydration", r"server-component", r"client-component", r"ssr\b", r"server-side-render")),
        Topic("stack-typescript", "TypeScript types & generics", (r"typescript", r"ts-generic", r"generics?\b", r"type-guard", r"union-type", r"discriminated-union")),
        Topic("stack-render-performance", "Render performance (memo, debounce, lazy)", (r"memoiz", r"react-memo", r"debounc", r"throttl", r"lazy-load", r"code-split", r"react-suspense")),
        Topic("stack-accessibility", "Accessibility (ARIA, focus, contrast)", (r"a11y", r"accessib", r"aria\b", r"focus-(trap|management)")),
    )),
    Sector("backend", "Backend", "api", "Servers, APIs and the logic behind them.", (
        Topic("stack-rest-api", "REST API design & HTTP status codes", (r"rest-?api", r"restful", r"http-(method|status|verb)", r"api-design")),
        Topic("stack-middleware", "Middleware & request pipelines", (r"middleware", r"request-pipeline", r"express-middleware")),
        Topic("stack-async", "Async code, promises & concurrency", (r"promise", r"async-await", r"asyncio", r"concurren", r"parallel-(requests|async)", r"event-loop")),
        Topic("stack-validation", "Input & schema validation (Zod, Pydantic)", (r"schema-validation", r"input-validation", r"zod\b", r"pydantic", r"request-validation")),
        Topic("stack-error-handling", "Error handling & retries", (r"error-handl", r"error-boundar", r"retr(y|ies)", r"exponential-backoff", r"exception-handl")),
        Topic("stack-caching", "Caching (Redis, HTTP caching)", (r"cach(e|ing)", r"redis", r"memcache")),
        Topic("stack-background-jobs", "Queues, cron & background jobs", (r"background-(job|task)", r"job-queue", r"message-queue", r"celery", r"cron\b", r"task-queue")),
        Topic("stack-realtime", "Realtime (WebSockets, SSE)", (r"websocket", r"server-sent", r"sse\b", r"real-?time", r"socket-io")),
        Topic("stack-rate-limiting", "Rate limiting & throttling", (r"rate-limit",)),
    )),
    Sector("data", "Databases", "database", "Storing and querying data safely.", (
        Topic("stack-sql", "SQL queries & joins", (r"sql-(quer|join|basics)", r"joins?\b", r"group-by", r"subquer")),
        Topic("stack-orm", "ORMs (Django ORM, Prisma, EF Core)", (r"orm\b", r"django-orm", r"prisma", r"queryset", r"entity-framework", r"sqlalchemy")),
        Topic("stack-migrations", "Schema migrations", (r"migration",)),
        Topic("stack-db-performance", "Indexes, N+1 & query performance", (r"db-index", r"database-index", r"indexing", r"n-plus-one", r"n1-quer", r"query-(performance|optimi)", r"select-related", r"eager-load")),
        Topic("stack-transactions", "Transactions & data integrity", (r"db-transaction", r"database-transaction", r"transactions?\b", r"atomic", r"race-condition", r"optimistic-lock", r"row-lock")),
        Topic("stack-nosql", "NoSQL stores (MongoDB, Firestore, DynamoDB)", (r"mongo", r"nosql", r"dynamo", r"firestore")),
    )),
    Sector("security", "Auth & security", "security", "Who can do what, and keeping it safe.", (
        Topic("stack-sessions-cookies", "Sessions & cookies", (r"session-(auth|cookie|management)", r"cookies?\b", r"httponly", r"samesite")),
        Topic("stack-jwt", "JWT & token-based auth", (r"jwt", r"bearer-token", r"access-token", r"refresh-token", r"token-(auth|rotation)")),
        Topic("stack-oauth", "OAuth, OpenID Connect & SSO", (r"oauth", r"oidc", r"openid", r"sso\b", r"social-login")),
        Topic("stack-password-hashing", "Password hashing (bcrypt, argon2)", (r"password-hash", r"bcrypt", r"argon", r"pbkdf2")),
        Topic("stack-web-security", "CSRF, XSS, CORS & injection", (r"csrf", r"xss", r"cors\b", r"sql-injection", r"injection", r"content-security-policy", r"sanitiz")),
        Topic("stack-secrets", "Secrets & environment config", (r"env-config", r"environment-variable", r"dotenv", r"secrets?-management", r"api-key-(storage|management)")),
        Topic("stack-rbac", "Roles & permissions (RBAC)", (r"rbac", r"role-based", r"permissions?\b", r"authori[sz]ation", r"access-control")),
    )),
    Sector("hosting", "Hosting & DevOps", "devops", "Shipping it and keeping it running.", (
        Topic("stack-docker", "Docker & containers", (r"docker", r"container", r"multi-stage")),
        Topic("stack-ci-cd", "CI/CD pipelines (GitHub Actions…)", (r"ci-cd", r"github-actions", r"ci-pipeline", r"continuous-(integration|deploy)", r"gitlab-ci")),
        Topic("stack-cloud-deploy", "Deploying to the cloud (Vercel, AWS, Azure)", (r"deploy", r"vercel", r"netlify", r"aws\b", r"azure", r"gcp\b", r"heroku", r"serverless", r"edge-function")),
        Topic("stack-dns-https", "Domains, DNS & HTTPS", (r"dns\b", r"https\b", r"tls\b", r"ssl\b", r"custom-domain", r"certificate")),
        Topic("stack-reverse-proxy", "Reverse proxies & load balancing", (r"nginx", r"reverse-proxy", r"load-balanc", r"cdn\b")),
        Topic("stack-observability", "Logging & monitoring", (r"logging", r"structured-log", r"monitor", r"observab", r"telemetry", r"sentry")),
    )),
    Sector("quality", "Testing & workflow", "testing", "Proving it works and working as a team.", (
        Topic("stack-unit-tests", "Unit tests (pytest, Jest, Vitest)", (r"unit-test", r"pytest", r"jest\b", r"vitest", r"test-driven", r"tdd\b")),
        Topic("stack-mocking", "Mocks, stubs & fixtures", (r"mock", r"stub", r"fixture", r"test-double")),
        Topic("stack-e2e-tests", "End-to-end tests (Playwright, Cypress)", (r"e2e", r"end-to-end", r"playwright", r"cypress")),
        Topic("stack-git", "Git branches, merges & PRs", (r"git-(branch|merge|rebase|workflow)", r"pull-request", r"merge-conflict")),
        Topic("stack-linting", "Linting & formatting", (r"lint", r"eslint", r"prettier", r"ruff\b", r"code-format")),
    )),
)

TOPICS: dict[str, Topic] = {t.slug: t for s in SECTORS for t in s.topics}
SECTOR_OF: dict[str, Sector] = {t.slug: s for s in SECTORS for t in s.topics}


def covering_topics(slug: str, known_topic_slugs) -> list[Topic]:
    """Which of the user's known topics cover this concept slug."""
    return [TOPICS[t] for t in known_topic_slugs if t in TOPICS and TOPICS[t].covers(slug)]
