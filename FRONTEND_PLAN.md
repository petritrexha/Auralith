# LearnLoop frontend redesign

## Architecture and contracts

The frontend is Django server-rendered HTML. There is no Node build or client framework. Templates live in `server/core/templates`; shared UI previously consisted of `base.html`, `_card.html`, and `_manage_nav.html`. Django staticfiles will serve the new local CSS and JavaScript. Existing Chart.js CDN charts will be replaced by accessible local HTML charts; Mermaid remains an optional enhancement with source fallback.

Preserve all URL names, session authentication, CSRF forms, model/service logic, permission checks, and plugin contracts. Member POST contracts include card actions (`known`, `mute`, `save`, `unsave`), concept `status`, settings submit names, password change, and token regeneration. Admin contracts include account creation/editing, activation, password/token reset, and report generation.

Routes: public `/`, `/login/`, `/logout/`, `/healthz`; member `/app/`, `/app/insights.json`, `/app/cards/`, card detail/action, `/app/concepts/`, concept status, setup/status/regenerate, settings and first-login; admin `/manage/`, insights, users/new/detail, concepts, reports/detail, activity, and `/django-admin/`. Plugin endpoints `/api/v1/ping` and `/api/v1/analyze` stay unchanged. Search uses the existing card feed GET filters. No client-side credentials or third-party UI libraries are introduced.

## Incremental implementation

1. Shared dark-first design tokens, original loop identity, sidebar/header, profile menu, responsive navigation, command search, focus states and reduced motion.
2. Landing/login, member overview, reusable learning cards and detail, concept statuses, setup and settings. Keep underlying forms and pagination intact. Use existing member category/activity insights.
3. Team overview, user management/detail, concept analytics, briefings and activity. Display real cost/token data and existing support/hotspot metrics. Use the mastery snapshots already stored in team briefings for a historical chart. Label these as irregular briefing snapshots, with an empty state before any reports exist; no new storage or reporting logic is needed.
4. Empty/error/loading feedback and standard Django error templates; check all template rendering and existing backend tests, then browser responsiveness and keyboard workflows where tooling is available.

## Visual direction

Graphite surfaces, mint accents, fine neutral borders, generous spacing, readable system typography and technical monospace. Original interlocking loop symbol. Small state transitions; no ornamental animation dependencies. Data charts include text values and remain readable without JavaScript.

## Completed validation

- All 26 Django tests pass, including the existing 19 and seven frontend integration tests. Django system checks and `git diff --check` pass.
- Headless Chrome: member and administration routes at 1440, 768, and 390 pixels; populated member pages, public pages, user details, and mastery snapshots additionally checked at 320 pixels. No page-level horizontal overflow remains.
- Browser workflows verified: login/logout, command search, mobile navigation/Escape, save/unsave, known/muted actions, settings submission, connection checks, and recovery after a failed connection request. No JavaScript errors were reported.
- Inspected desktop and mobile screenshots against an isolated demo SQLite database under the ignored `.venv` directory. Application data was not changed.
- Backend adjustments are limited to a read-only query for existing report snapshots and styled staff-access denial. No migrations, API changes, dependency changes, authentication changes, or reporting logic changes.

## Motion and visual depth follow-up

Added a separate, reusable native-browser motion layer: CSS aurora glows and a faint grid, pointer-positioned card lighting, subtle hero perspective, staggered IntersectionObserver entrances, Web Animations API chart growth, and menu/dialog transitions. Pointer updates are batched with requestAnimationFrame; there is no continuous JavaScript render loop or added package.

The shared Motion toggle persists locally. System reduced-motion preferences override it, hidden tabs pause effects, and content remains visible if JavaScript is unavailable. Browser checks passed at 320, 390, 768, and 1440 pixels, including live preference changes, persisted toggling, search, mobile navigation, and saving a card. All 26 Django tests still pass; this follow-up changes no backend files.
