# CorpLunch

Учебный проект: корпоративные обеды в офисе. Сотрудники заранее планируют блюда из каталога [Mealty](https://www.mealty.ru), в день поставки система собирает сводный заказ **по актуальным ценам сайта**. Оформление на Mealty остаётся ручным — закупки выгружают список и размещают заказ сами.

Репозиторий и код: `corplunch`.

## Зачем это нужно

В офисе каждый выбирает блюда наперёд, но цена и наличие на Mealty меняются. Система разделяет две вещи:

- **план** — что сотрудник хочет на конкретную дату (ориентировочная цена);
- **заказ дня** — что реально закупаем, уже с текущей ценой и без снятых с меню позиций.

Отдел закупок видит сводку, экспорт и статистику по людям, отделам и отклонению «план vs факт».

## Стек

| Слой | Технология |
|------|------------|
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic |
| Frontend | React, TypeScript, Vite, TanStack Query |
| БД | PostgreSQL |
| Задачи по расписанию | APScheduler |
| Локальный запуск | Docker Compose |

## Документация

| Документ | О чём |
|----------|--------|
| [docs/vision.md](docs/vision.md) | Цели, MVP, что не делаем |
| [docs/architecture.md](docs/architecture.md) | Модульный монолит, пакеты, потоки данных |
| [docs/data-model.md](docs/data-model.md) | Таблицы, статусы, правило цены |
| [docs/api.md](docs/api.md) | Контракт HTTP API |
| [docs/roles.md](docs/roles.md) | Роли и пользовательские сценарии |
| [docs/mealty.md](docs/mealty.md) | Парсер каталога Mealty |
| [docs/team.md](docs/team.md) | Тимлид, писатель, QA; кто что пишет |
| [docs/sprints.md](docs/sprints.md) | Этапы 0–4, сроки ~9 недель |
| [docs/process.md](docs/process.md) | Жизненный цикл ПО, Scrum-lite, GitHub Flow |
| [docs/ui.md](docs/ui.md) | Черновик экранов и тон интерфейса |
| [docs/demo.md](docs/demo.md) | Сценарий защиты / демо |

Код приложения в этом репозитории пока не реализован: сначала фиксируем договорённости команды.

## Роли в системе

- **employee** — каталог, план на даты вперёд, свои позиции и предупреждения (сняли блюдо / изменилась цена).
- **procurement** — сводка на дату, закрытие приёма, CSV/XLSX, отметка «заказ размещён», статистика.
- **admin** — пользователи, отделы, cutoff, город Mealty, дневной лимит.

Демо-пользователи (после реализации seed):

| Email | Пароль | Роль |
|-------|--------|------|
| `employee@kis.local` | `employee` | сотрудник |
| `employee2@kis.local` | `employee2` | сотрудник |
| `procurement@kis.local` | `procurement` | закупки |
| `admin@kis.local` | `admin` | администратор |

## Как будем запускать (после реализации)

```bash
docker compose up --build
```

- веб: `http://localhost:5173`
- API и OpenAPI: `http://localhost:8000/docs`

Один `docker compose up` поднимает PostgreSQL, backend и frontend. Backend — один FastAPI с внутренними модулями.

Команды seed (появятся на этапах 0–1, точные имена в CLI):

```bash
docker compose exec api python -m app.cli seed-users
docker compose exec api python -m app.cli sync-from-fixture
```

- `seed-users` — отделы и демо-учётки, включая двух сотрудников (этап 0).
- `sync-from-fixture` — каталог из `backend/tests/fixtures/mealty_catalog.html`, без запроса на mealty.ru (этап 1). Для демо без живого сайта.

Цены в API и БД — целые **копейки** (`*_kopecks`); UI делит на 100 и показывает ₽. Авторизация — только `Authorization: Bearer <jwt>`, без cookie.

Контракт API не меняем без согласования в PR.

## Команда

Классические роли совмещаются с разработкой (подробно — [docs/team.md](docs/team.md)):

- **Бондарь А.Р.** — тимлид, ведущий разработчик, DevOps (ядро backend, Compose, ревью).
- **Пягай** — технический писатель и простой backend (docs, auth/admin, seed, CLI фикстуры, хелперы лимита/429, pytest по контракту, CSV по шаблону).
- **Шишков** — frontend и QA (все экраны включая админку, чек-листы, регресс, фикстура HTML).

Сроки и пересечение этапов: [docs/sprints.md](docs/sprints.md). Жизненный цикл и метод разработки: [docs/process.md](docs/process.md).

## Правило цены

В плане сотрудник видит **последнюю известную** цену из снимка каталога (`price_kopecks`). В день заказа (после cutoff) система синхронизирует Mealty, пишет `actual_price_kopecks` и помечает исчезнувшие блюда как `unavailable`. В сводку закупок входят только доступные позиции.

Cutoff по умолчанию: **16:00 предыдущего дня** (настраивается).
