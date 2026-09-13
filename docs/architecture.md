# Архитектура

## Обзор

**CorpLunch** — монорепозиторий, **модульный монолит** на этапах 0–4: один FastAPI, один Postgres, пакеты с жёсткими границами. Каталог приходит из адаптера `MealtyProvider` (HTML главной [mealty.ru](https://www.mealty.ru)). Другие сайты — тот же `FoodProvider`.

Трое в команде: Бондарь А.Р. — ядро и DevOps, Пягай — простой backend и docs, Шишков — React и QA ([team.md](team.md)). Backend — один сервис FastAPI.

```mermaid
flowchart LR
  Mealty[mealty.ru HTML]
  Parser[MealtyProvider]
  Catalog[(catalog + price_history)]
  Employee[Сотрудник]
  Plan[planned_items]
  DayJob[cutoff job]
  Snapshot[order_day snapshot]
  Procurement[Закупки]

  Mealty --> Parser --> Catalog
  Employee --> Plan
  Catalog --> Employee
  Plan --> DayJob
  Catalog --> DayJob
  DayJob --> Snapshot
  Snapshot --> Procurement
```

## Структура репозитория (целевая)

```
kis/
  backend/                 FastAPI, SQLAlchemy 2, Alembic, pytest
    app/
      auth/                JWT, зависимости ролей
      users/               пользователи, отделы
      catalog/             блюда, категории, история цен
      providers/           FoodProvider, MealtyProvider
      planning/            планы сотрудников
      orders/              дневной снимок, агрегат, экспорт
      stats/               отчёты закупок
      jobs/                APScheduler: sync + cutoff
  frontend/                Vite + React + TypeScript + TanStack Query
  docker-compose.yml
  docs/
  README.md
```

Контракт между командами — OpenAPI (`/docs` у FastAPI). Клиент на фронте лучше генерировать из схемы, а не писать URL руками.

## Модули backend

| Пакет | Ответственность | Кто использует |
|-------|-----------------|----------------|
| `auth` | логин, JWT, `CurrentUser`, проверка роли | все |
| `users` | CRUD пользователей и отделов, настройки системы | admin, статистика |
| `catalog` | upsert блюд, `price_history`, выдача текущего меню | employee, parser, cutoff |
| `providers` | нормализация внешнего каталога, без знания БД заказов | catalog sync |
| `planning` | план на дату, qty, planned_price, cutoff-блокировка | employee |
| `orders` | office_order, агрегация, CSV/XLSX, статус placed | procurement |
| `stats` | агрегаты за период | procurement, admin |
| `jobs` | расписание sync каталога и cutoff | инфраструктура |

Граница модулей: `providers` возвращает `NormalizedDish`, `catalog` пишет в БД, `planning` не ходит на Mealty напрямую.

## Интерфейс провайдера

```python
class FoodProvider(Protocol):
    source: str  # "mealty"

    async def fetch_catalog(self) -> list[NormalizedDish]:
        ...
```

`NormalizedDish`:

| Поле | Смысл |
|------|--------|
| `external_id` | стабильный id на сайте (`data-product_id`) |
| `name`, `subtitle` | название и уточнение |
| `category` | `breakfast`, `salad`, `soup`, `main_dish`, … |
| `price`, `old_price` | текущая и зачёркнутая цена |
| `weight_g` | вес |
| `proteins`, `fats`, `carbs`, `calories` | КБЖУ |
| `image_url` | абсолютный URL картинки |
| `available` | есть в свежем снимке |

В БД блюдо уникально парой `source + external_id` (например `mealty` + `875`).

## Фоновые задачи

1. **Catalog sync** — 1–2 раза в сутки (утро). Пишет/обновляет `dishes`, добавляет строку в `price_history`, блюда, которых нет в свежем HTML, помечает `available=false`.
2. **Cutoff job** — в настроенное время (по умолчанию 16:00) для **завтрашней** даты: синхронизирует каталог, переводит планы `draft → locked → priced`, заполняет `actual_price` / `unavailable`, собирает `office_order`.

Ручной `POST /catalog/sync` доступен закупкам и админу, если нужно обновить меню не дожидаясь cron.

## Frontend

Три экрана MVP:

1. Каталог + календарь плана — сотрудник.
2. Сводка дня — закупки.
3. Статистика — закупки/админ.

JWT в заголовке `Authorization: Bearer …` (допустима httpOnly cookie — выбрать один способ и не смешивать). Демо-вход без SSO.

## Инфраструктура

Docker Compose MVP: `db`, `api`, `web`. Backend читает `DATABASE_URL`, `JWT_SECRET`, `MEALTY_CITY`, `CUTOFF_TIME`. Frontend проксирует `/api` на backend.


## Принципы командной разработки

- Ветки `feature/…`, PR в `main`.
- Миграции Alembic только в своём PR, без ручного SQL на общей БД.
- Ломающий OpenAPI — отдельное согласование в описании PR.
- Тесты парсера используют фикстуру HTML, не живой сайт.
