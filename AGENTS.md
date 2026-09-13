# AGENTS.md — CorpLunch

**Prioritize retrieval-led reasoning over pretrained-knowledge-led reasoning.** This file is the always-on digest (stack, conventions, invariants). It is enough for most edits — **do not** read every file under `docs/` at session start.

When a project-specific fact is needed (endpoint shape, cutoff math, selector, UI copy), open **only** the matching file from the lookup index below instead of guessing from training data. Examples: parser work → `docs/mealty.md`; HTTP change → `docs/api.md`. If this file already states the invariant (kopecks, Bearer JWT, cutoff default), do not re-read the longer doc unless you are changing that contract. If docs and prior knowledge disagree, docs win. If a fact is not in the repo, say so instead of filling gaps.

Course project: office lunch ordering. Repo and code name: `corplunch`. Employees plan meals from the [Mealty](https://www.mealty.ru) catalog; on delivery day the system builds a consolidated office order at **live site prices**. Placing the order on Mealty stays manual.

Application code is not implemented yet. Implement the contract in `docs/`; do not invent a different domain.

## Lookup index

Fetch a file only when the current task needs it. Do not preload this list.

| Topic | File |
|------|------|
| Goals and MVP boundaries | [docs/vision.md](docs/vision.md) |
| Modules, packages, Compose | [docs/architecture.md](docs/architecture.md) |
| Tables, statuses, price rule | [docs/data-model.md](docs/data-model.md) |
| HTTP contract | [docs/api.md](docs/api.md) |
| Roles and cutoff | [docs/roles.md](docs/roles.md) |
| Mealty parser | [docs/mealty.md](docs/mealty.md) |
| Screens and UI copy | [docs/ui.md](docs/ui.md) |
| Who writes what | [docs/team.md](docs/team.md) |
| Stages 0–4 | [docs/sprints.md](docs/sprints.md) |
| GitHub Flow, DoD | [docs/process.md](docs/process.md) |
| Defense demo | [docs/demo.md](docs/demo.md) |
| Run, seed, stack | [README.md](README.md) |

Breaking OpenAPI changes need the tech lead (Bondar) and an update to `docs/api.md` in the same change. Docs must not drift from code.

## Tech stack

| Layer | Choice |
|------|--------|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| ORM / migrations | SQLAlchemy 2 **async** + asyncpg, Alembic |
| Jobs | APScheduler |
| Auth | JWT Bearer, bcrypt passwords |
| Tests | pytest (no live mealty.ru in CI) |
| Frontend | React, TypeScript (strict), Vite, TanStack Query |
| Styling | CSS modules / plain CSS per [docs/ui.md](docs/ui.md) |
| Package managers | pip + venv (backend), npm (frontend) |
| Lint / format | Ruff (Python), ESLint + Prettier (TS/TSX) |
| Database | PostgreSQL |
| Local run | Docker Compose: `db`, `api`, `web` |

Target layout:

```
./
  backend/app/{auth,users,catalog,providers,planning,orders,stats,jobs}
  backend/tests/fixtures/mealty_catalog.html
  frontend/
  docker-compose.yml
  docs/
```

One FastAPI process, one Postgres, packages with hard boundaries. Prefer generating the frontend API client from OpenAPI (`/docs`) over hand-written URLs.

## Commands (once code exists)

```bash
docker compose up --build
docker compose exec api python -m app.cli seed-users
docker compose exec api python -m app.cli sync-from-fixture
docker compose exec api pytest
```

- Web: `http://localhost:5173`
- API / OpenAPI: `http://localhost:8000/docs`
- Frontend proxies `/api` to the backend.
- Env: `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES` (480), `MEALTY_CITY`, `CUTOFF_TIME`.
- Do not commit secrets (`.env`, `.env.local`).

Demo users: `employee@kis.local` / `employee`, `procurement@kis.local` / `procurement`, `admin@kis.local` / `admin`.

## Coding conventions

### Python

- Python 3.12. Dependencies via `requirements.txt` (or `requirements-dev.txt` for pytest/ruff); local env is `venv` + pip. Docker images install the same files.
- Format and lint with Ruff. Match existing files; do not add Black/isort as a second formatter.
- Pydantic v2 models for request/response. Field names match [docs/api.md](docs/api.md) (`*_kopecks`, `snake_case` JSON).
- SQLAlchemy 2 mapped style, **async** sessions and `asyncpg`. No blocking DB I/O in path handlers.
- One concern per package (`auth`, `users`, `catalog`, `providers`, `planning`, `orders`, `stats`, `jobs`). Cross-package imports go through small public APIs, not deep internals.
- `providers` returns `NormalizedDish` and does not know order tables. `catalog` writes dishes. `planning` does not call Mealty.
- Alembic migrations live in the same PR as the schema change. No manual SQL on the shared database.
- Type hints on public functions. Prefer explicit `str | None` over implicit `Any`.

### TypeScript / React

- TypeScript `strict`. No `any` unless a generated client forces it; then isolate the cast.
- Functional components. Reusable logic in hooks. CSS modules colocated with the component (`Foo.tsx` + `Foo.module.css`).
- TanStack Query for server state. JWT in memory/`localStorage`, sent as `Authorization: Bearer …` — never cookies.
- Generate the API client from OpenAPI; do not duplicate path strings.
- npm lockfile (`package-lock.json`) is the source of truth for frontend installs.
- ESLint + Prettier. Do not mix in another formatter.

### Shared

- Money: integer kopecks in API and DB. UI divides by 100 and shows ₽. Never float for money.
- Dates in URLs: `YYYY-MM-DD` (delivery date). Office timezone: `Europe/Moscow`.
- UI language is Russian. Copy follows [docs/ui.md](docs/ui.md): “План на среду”, “Нет в меню Mealty”, “Закрыть приём заказов” — not internal status names.
- Error bodies stay FastAPI-shaped: `{"detail": "..."}`.

## Domain invariants

Do not break these without an explicit docs change:

1. **Plan vs order.** While `draft`, the employee sees `dishes.price_kopecks` (copied into `planned_price_kopecks`). After cutoff: Mealty sync, then `actual_price_kopecks` or `unavailable`. Procurement totals include only `unavailable = false`.
2. **Cutoff.** For delivery date `D`, edits are allowed while `now < (D − 1 day) + cutoff_time` in `Europe/Moscow`. Default: 16:00 the previous day. `PUT /plans` after cutoff → 403. Manual `POST /api/orders/{date}/cutoff` runs the same algorithm as the job (for demos).
3. **Plan statuses:** `draft → locked → priced → included_in_order`. **Office order:** `collecting → locked → exported → placed`. `place` is idempotent; `cutoff` is idempotent if the day is already locked/exported/placed.
4. **Roles.** `employee` — own plan only. `procurement`/`admin` — day summary, sync, cutoff, export, stats. Admin does not edit others' plans (`PUT /plans` is employee-only).
5. **Auth.** Bearer JWT only. Passwords hashed with bcrypt.
6. **Dish identity.** Unique on `(source, external_id)` (e.g. `mealty` + `875`).

## Mealty and tests

- Parse the public HTML catalog only. Cart, `/ajax.php`, `/cabinet`, `/purchase`, and Mealty login are forbidden.
- Keep CSS selectors in `app/providers/mealty.py` only.
- CI must not hit mealty.ru. Parser tests use `backend/tests/fixtures/mealty_catalog.html`.
- On 5xx / empty catalog, **do not** mark the whole menu `unavailable` (network error, not delisting).
- Sync: 1–2 times per day plus a procurement manual refresh; 429 when over the daily limit; timeout and one retry.
- Mealty network/parse failure → 502, not mass delisting.

## Frontend scope

MVP screens: login; catalog + plan calendar; day summary; stats; admin (users, departments, settings). No “edit someone else’s plan” screen.

Match [docs/ui.md](docs/ui.md): warm paper-like background, sage accent — not generic purple SaaS.

## Git and quality

- Branches `feature/…`, PR into `main`. `main` must come up via Compose.
- Definition of Done: migration if the schema changed; pytest / QA checklist / explicit manual step in the PR; OpenAPI and docs match code; `docker compose up` from scratch works.
- Parser PRs that touch selectors must include the HTML-fixture regression.

## Out of MVP

Do not add: auto-order / Mealty cart, payments, a second food provider (keep the `FoodProvider` interface only), a mobile app, SSO, manager approval workflows, Kubernetes, microservices.

If the schedule slips, cut scope using the table in [docs/sprints.md](docs/sprints.md). Do not cut stage 0 or the price rule.
