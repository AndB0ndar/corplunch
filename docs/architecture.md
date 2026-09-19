# Архитектура

## Обзор

**CorpLunch** — монорепозиторий, **модульный монолит** на этапах 0–4: один FastAPI, один Postgres, пакеты с жёсткими границами. Каталог приходит из адаптера `MealtyProvider` (HTML главной [mealty.ru](https://www.mealty.ru)). Другие сайты — тот же `FoodProvider`.

Трое в команде: Бондарь А.Р. — ядро и DevOps, Пягай — простой backend и docs, Шишков — React и QA ([team.md](team.md)). Backend — один сервис FastAPI.

Схема — [C4](https://c4model.com): сначала система как чёрный ящик (контекст), затем процессы из Compose (контейнеры). Пакеты внутри FastAPI — не контейнеры, они в таблице «Модули backend».

### Контекст (C4, уровень 1)

Кто пользуется CorpLunch и с чем система связана снаружи. Оформление заказа на Mealty **не автоматизируется**: закупки переносят сводку вручную.

```mermaid
C4Context
    title CorpLunch — системный контекст

    Enterprise_Boundary(office, "Офис") {
        Person(employee, "Сотрудник", "Смотрит каталог и составляет свой план на дату доставки")
        Person(procurement, "Закупки", "Сводка дня, экспорт, cutoff; заказ на Mealty размещает вручную")
        Person(admin, "Администратор", "Пользователи, отделы, время cutoff, город, лимиты")
        System(corplunch, "CorpLunch", "Планы сотрудников и сводный заказ офиса по живым ценам каталога")
    }

    System_Ext(mealty, "mealty.ru", "Публичный HTML-каталог. Корзина, кабинет и оформление заказа — вне MVP")

    Rel(employee, corplunch, "План и меню")
    Rel(procurement, corplunch, "Сводка, экспорт, sync, cutoff")
    Rel(admin, corplunch, "Учётки и настройки")
    Rel(corplunch, mealty, "Читает каталог", "HTTPS, HTML")
    Rel(procurement, mealty, "Переносит сводку и оформляет заказ вручную")
```

- **Сотрудник** видит только свой план; чужие не редактирует никто (`PUT /plans` — только employee).
- **Закупки** работают со сводкой офиса. Связь с mealty.ru у них ручная, не через API CorpLunch.
- **CorpLunch → mealty.ru** — только публичная HTML-витрина. Парсер не ходит в корзину и `/cabinet`.

### Контейнеры (C4, уровень 2)

Три процесса Compose: браузерное SPA, один FastAPI, Postgres. Jobs (sync каталога и cutoff) крутятся **в том же процессе**, что и API.

```mermaid
C4Container
    title CorpLunch — контейнеры (docker compose: web, api, db)

    Person(users, "Пользователи", "employee / procurement / admin — разные экраны одной SPA")

    Container_Boundary(system, "CorpLunch") {
        Container(web, "web", "React, TypeScript, Vite", "SPA: вход, каталог и план, сводка дня, статистика, админка. JWT в Authorization, без cookie")
        Container(api, "api", "Python 3.12, FastAPI, APScheduler", "HTTP API и фоновые задачи. Парсер Mealty, cutoff, экспорт CSV/XLSX")
        ContainerDb(db, "db", "PostgreSQL", "Пользователи, dishes и price_history, планы, office_order")
    }

    System_Ext(mealty, "mealty.ru", "Публичный HTML-каталог")

    Rel(users, web, "Экраны в браузере", "HTTPS")
    Rel(web, api, "JSON, OpenAPI", "HTTPS, Bearer JWT; dev-прокси /api")
    Rel(api, db, "Читает и пишет", "asyncpg")
    Rel(api, mealty, "fetch_catalog", "HTTPS GET, HTML")
```

`web` не ходит в Postgres и на Mealty: только в `api`. `api` — модульный монолит (пакеты `auth`, `catalog`, `planning`, `orders`, …), не набор микросервисов.

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

Контракт между командами — OpenAPI (`/docs` у FastAPI). Клиент на фронте в итоге лучше генерировать из схемы, а не писать URL руками. На этапе 0 Бондарь кладёт тонкий `api.ts`; генерацию включаем, когда стабильны login и `GET /api/me`.

## Модули backend

| Пакет | Ответственность | Кто использует |
|-------|-----------------|----------------|
| `auth` | логин, JWT, `CurrentUser`, проверка роли | все |
| `users` | CRUD пользователей и отделов, настройки системы | admin, статистика |
| `catalog` | upsert блюд, `price_history`, выдача текущего меню | employee, parser, cutoff |
| `providers` | нормализация внешнего каталога, без знания БД заказов | catalog sync |
| `planning` | план на дату, qty, `planned_price_kopecks`, cutoff-блокировка | employee |
| `orders` | office_order, агрегация, CSV/XLSX, ручной cutoff, статус placed | procurement |
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

`NormalizedDish` (цены сразу в копейках, как в `dishes`):

| Поле | Смысл |
|------|--------|
| `external_id` | стабильный id на сайте (`data-product_id`) |
| `seller_product_id` | `data-seller-product_id`, nullable |
| `name`, `subtitle` | название и уточнение |
| `description` | текст карточки, nullable |
| `category` | `breakfast`, `salad`, `soup`, `main_dish`, … |
| `price_kopecks`, `old_price_kopecks` | текущая и зачёркнутая цена |
| `weight_g` | вес |
| `proteins`, `fats`, `carbs`, `calories` | КБЖУ |
| `image_url` | абсолютный URL картинки |
| `available` | есть в свежем снимке |

В БД блюдо уникально парой `source + external_id` (например `mealty` + `875`).

## Фоновые задачи

1. **Catalog sync** — 1–2 раза в сутки (утро). Пишет/обновляет `dishes`, добавляет строку в `price_history`, блюда, которых нет в свежем HTML, помечает `available=false`.
2. **Cutoff job** — в настроенное время (по умолчанию 16:00) для **завтрашней** даты: синхронизирует каталог, переводит планы `draft → locked → priced → included_in_order`, заполняет `actual_price_kopecks` / `unavailable`, собирает `office_order`.

Ручной `POST /api/catalog/sync` доступен закупкам, если нужно обновить меню не дожидаясь cron. Ручной `POST /api/orders/{date}/cutoff` — тот же алгоритм, что у job, для указанной даты (демо, не ждать 16:00).

## Frontend

Экраны MVP (все — Шишков, по [ui.md](ui.md)):

1. Вход.
2. Каталог + календарь плана — сотрудник.
3. Сводка дня — закупки (в т.ч. «закрыть приём»).
4. Статистика — закупки/админ.
5. Пользователи, отделы, настройки — админ. Стартовать, как только живы `/api/admin/users` и `/api/admin/settings` (Пягай), не к защите.

JWT только в заголовке `Authorization: Bearer …` (без cookie). Демо-вход без SSO.

## Инфраструктура

Docker Compose MVP: `db`, `api`, `web`. Backend читает `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES` (по умолчанию 480), `MEALTY_CITY`, `CUTOFF_TIME`. Пароли — bcrypt. Frontend проксирует `/api` на backend.


## Принципы командной разработки

- Коммиты сразу в `main`. Ветки и PR по желанию, не как шлюз.
- Миграции Alembic в том же изменении, что и схема, без ручного SQL на общей БД.
- Ломающий OpenAPI — отдельное согласование с тимлидом в том же изменении.
- Тесты парсера используют фикстуру HTML, не живой сайт.
