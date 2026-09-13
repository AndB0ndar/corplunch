# HTTP API

Базовый префикс: `/api`. JSON, UTF-8. Ошибки в формате FastAPI/`{"detail": "..."}`.

Авторизация: заголовок `Authorization: Bearer <jwt>` на всех методах, кроме логина.

Роли: `employee`, `procurement`, `admin`. Где написано «закупки» — достаточно `procurement` или `admin`.

## Auth и профиль

### `POST /api/auth/login`

Тело: `{ "email": string, "password": string }`

Ответ 200: `{ "access_token": string, "token_type": "bearer" }`

401 — неверный логин/пароль.

### `GET /api/me`

Ответ: пользователь (id, email, full_name, role, department, daily_limit).

## Каталог

### `GET /api/catalog`

Query: `category?`, `q?` (поиск по названию), `available_only` (default true).

Ответ: список блюд текущего снимка.

Доступ: все авторизованные.

### `POST /api/catalog/sync`

Запускает `MealtyProvider.fetch_catalog()` и upsert в БД.

Ответ: `{ "upserted": int, "unavailable": int, "recorded_at": iso }`

Доступ: закупки. 429, если превышен дневной лимит запросов к Mealty.

## Планы сотрудника

Дата в URL: `YYYY-MM-DD` (дата **доставки**).

### `GET /api/plans/{date}`

Свой план на дату (employee) или любой по `?user_id=` (закупки/админ).

Ответ: план, позиции, суммы planned/actual, флаги unavailable, `editable: bool`.

Если плана нет — пустой draft-шаблон, `editable` по cutoff.

### `PUT /api/plans/{date}`

Тело: `{ "items": [ { "dish_id": int, "qty": int } ] }`

Полная замена состава. Сервер проставляет `planned_price` из текущего каталога.

403 — после cutoff или чужой план. 409 — блюдо unavailable / не найдено. 422 — превышен дневной лимит, если он задан.

Доступ: employee (свой план), admin.

## Сводный заказ (закупки)

### `GET /api/orders/{date}`

Сводка:

- статус office_order;
- агрегат по блюдам (название, qty, цена, сумма);
- разбивка по сотрудникам и отделам;
- итог, сумма unavailable (не вошло в закупку);
- дельта план vs факт.

Доступ: закупки.

### `GET /api/orders/{date}/export.csv`

CSV: колонки `external_id, name, qty, unit_price, line_total`.

Переводит статус `locked → exported` (если ещё не placed).

### `GET /api/orders/{date}/export.xlsx`

Тот же набор + лист «По сотрудникам».

### `POST /api/orders/{date}/place`

Тело необязательно. Ставит `placed`, пишет кто и когда.

403, если ещё `collecting` (cutoff не прошёл). Идемпотентно, если уже `placed`.

## Статистика

### `GET /api/stats/summary`

Query: `from`, `to` (даты доставки, обязательны), `department_id?`.

Ответ:

- `total_actual` — сколько потратили;
- `total_planned` — сколько планировали;
- `delta` — факт − план;
- `unavailable_count` — сколько позиций выпало;
- `by_department[]` — сумма и число заказов;
- `by_employee[]` — топ или полный список;
- `top_dishes[]` — qty и сумма;
- `price_changes[]` — блюда с заметной дельтой.

Доступ: закупки.

## Админка (минимум)

Нужно для демо и seed, можно упростить до «только seed», но контракт лучше заложить:

- `GET/POST /api/admin/users`
- `PATCH /api/admin/users/{id}` — роль, отдел, лимит, is_active
- `GET/PUT /api/admin/settings` — cutoff, город, лимит

Доступ: `admin`.

## Коды ошибок (договорённость)

| Код | Когда |
|-----|--------|
| 400 | невалидная дата, пустой состав при lock |
| 401 | нет/протух JWT |
| 403 | роль или cutoff |
| 404 | нет блюда / пользователя |
| 409 | конфликт статуса заказа |
| 429 | слишком частый sync Mealty |
| 502 | Mealty не ответил / HTML не распарсился |

## Версионирование

Пока один контракт без `/v1`. Ломающие поля — только через PR с пометкой в описании. Фронт не должен зависеть от порядка полей.
