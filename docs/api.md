# HTTP API

Базовый префикс: `/api`. JSON, UTF-8. Ошибки в формате FastAPI/`{"detail": "..."}`.

Деньги во всех JSON-полях — целые **копейки** (`*_kopecks`). Те же имена, что в [data-model.md](data-model.md). UI делит на 100 и показывает ₽.

Авторизация: только заголовок `Authorization: Bearer <jwt>` на всех методах, кроме логина и `GET /api/health`. Cookie не используем. TTL токена — `JWT_EXPIRE_MINUTES` (по умолчанию 480).

Роли: `employee`, `procurement`, `admin`. Где написано «закупки» — достаточно `procurement` или `admin`.

## Служебное

### `GET /api/health`

Без авторизации. Liveness процесса и ping Postgres.

Ответ 200:

```json
{ "status": "ok", "database": "up" }
```

503 — `{"detail": "Database unavailable"}`, если API не достучался до БД.

## Auth и профиль

### `POST /api/auth/login`

Тело: `{ "email": string, "password": string }`

Ответ 200:

```json
{ "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "token_type": "bearer" }
```

401 — неверный логин/пароль.

### `GET /api/me`

```json
{
  "id": 1,
  "email": "employee@kis.local",
  "full_name": "Иван Сотрудник",
  "role": "employee",
  "department": { "id": 1, "name": "Разработка" },
  "daily_limit_kopecks": null
}
```

## Каталог

### `GET /api/catalog`

Query: `category?`, `q?` (поиск по названию), `available_only` (default true).

Доступ: все авторизованные.

```json
[
  {
    "id": 12,
    "source": "mealty",
    "external_id": "875",
    "seller_product_id": "100875",
    "name": "Картофельные ньокки с грибами",
    "subtitle": "со сливочным соусом",
    "description": null,
    "category": "main_dish",
    "price_kopecks": 41000,
    "old_price_kopecks": 45000,
    "weight_g": 300,
    "proteins": 8.1,
    "fats": 12.0,
    "carbs": 42.0,
    "calories": 310,
    "image_url": "https://www.mealty.ru/upload/example.jpg",
    "available": true
  }
]
```

### `POST /api/catalog/sync`

Запускает `MealtyProvider.fetch_catalog()` и upsert в БД.

```json
{ "upserted": 230, "unavailable": 4, "recorded_at": "2026-09-15T07:05:00+03:00" }
```

Доступ: закупки. 429, если превышен дневной лимит запросов к Mealty. 502 — Mealty не ответил / HTML не распарсился.

## Планы сотрудника

Дата в URL: `YYYY-MM-DD` (дата **доставки**).

### `GET /api/plans/{date}`

Свой план на дату (employee) или любой по `?user_id=` (закупки/админ).

Если плана нет — пустой draft-шаблон, `editable` по cutoff.

```json
{
  "id": 41,
  "user_id": 1,
  "delivery_date": "2026-09-16",
  "status": "draft",
  "editable": true,
  "planned_total_kopecks": 82000,
  "actual_total_kopecks": null,
  "items": [
    {
      "dish_id": 12,
      "name": "Картофельные ньокки с грибами",
      "qty": 2,
      "planned_price_kopecks": 41000,
      "actual_price_kopecks": null,
      "unavailable": false
    }
  ]
}
```

### `PUT /api/plans/{date}`

Тело: `{ "items": [ { "dish_id": int, "qty": int } ] }`

Полная замена состава. Сервер проставляет `planned_price_kopecks` из текущего каталога.

403 — после cutoff или чужой план. 409 — блюдо unavailable / не найдено. 422 — превышен дневной лимит, если он задан.

Доступ: только employee, только свой план. Админ чужие планы не редактирует (для демо достаточно seed).

## Сводный заказ (закупки)

### `GET /api/orders/{date}`

```json
{
  "delivery_date": "2026-09-16",
  "status": "locked",
  "totals": {
    "planned_kopecks": 164000,
    "actual_kopecks": 170000,
    "delta_kopecks": 6000,
    "unavailable_count": 1
  },
  "items": [
    {
      "dish_id": 12,
      "external_id": "875",
      "name": "Картофельные ньокки с грибами",
      "qty": 4,
      "unit_price_kopecks": 42500,
      "line_total_kopecks": 170000
    }
  ],
  "by_employee": [
    {
      "user_id": 1,
      "full_name": "Иван Сотрудник",
      "department_id": 1,
      "department_name": "Разработка",
      "actual_total_kopecks": 85000,
      "unavailable_count": 0
    }
  ]
}
```

Доступ: закупки.

### `GET /api/orders/{date}/export.csv`

CSV: колонки `external_id, name, qty, unit_price_kopecks, line_total_kopecks`.

Переводит статус `locked → exported` (если ещё не placed).

### `GET /api/orders/{date}/export.xlsx`

Тот же набор + лист «По сотрудникам».

### `POST /api/orders/{date}/cutoff`

Ручное закрытие дня: тот же алгоритм, что у cutoff job, для указанной даты доставки (sync каталога → планы `draft → locked → priced → included_in_order` → `office_order` в `locked`). Нужен для демо, чтобы не ждать 16:00.

Доступ: закупки. Идемпотентно, если день уже `locked` / `exported` / `placed` (200 без изменений).

### `POST /api/orders/{date}/place`

Тело необязательно. Ставит `placed`, пишет кто и когда.

403, если ещё `collecting` (cutoff не прошёл). Идемпотентно, если уже `placed`.

## Статистика

### `GET /api/stats/summary`

Query: `from`, `to` (даты доставки, обязательны), `department_id?`.

Доступ: закупки.

```json
{
  "from": "2026-09-14",
  "to": "2026-09-18",
  "total_planned_kopecks": 820000,
  "total_actual_kopecks": 805000,
  "delta_kopecks": -15000,
  "unavailable_count": 3,
  "by_department": [
    { "department_id": 1, "name": "Разработка", "actual_kopecks": 500000, "order_count": 4 }
  ],
  "by_employee": [
    { "user_id": 1, "full_name": "Иван Сотрудник", "actual_kopecks": 170000, "order_count": 4 }
  ],
  "top_dishes": [
    { "dish_id": 12, "name": "Картофельные ньокки с грибами", "qty": 12, "actual_kopecks": 510000 }
  ],
  "price_changes": [
    {
      "dish_id": 12,
      "name": "Картофельные ньокки с грибами",
      "planned_price_kopecks": 41000,
      "actual_price_kopecks": 42500
    }
  ]
}
```

## Админка

Контракт нужен в MVP: админ заводит отделы и сотрудников и меняет cutoff/город с экрана, не только через seed. API — Пягай; экран — Шишков, как только живы эти методы ([team.md](team.md)). `seed-users` создаёт демо-учётки на этапе 0, в том числе **двух сотрудников**.

Доступ: `admin`.

### `GET /api/admin/departments`

```json
[{ "id": 1, "name": "Разработка" }, { "id": 2, "name": "Закупки" }]
```

### `POST /api/admin/departments`

Тело: `{ "name": "Маркетинг" }` → 201 и объект отдела.

### `PATCH /api/admin/departments/{id}`

Тело: `{ "name": string }`.

### `GET /api/admin/users`

Список без `password_hash`.

```json
[
  {
    "id": 1,
    "email": "employee@kis.local",
    "full_name": "Иван Сотрудник",
    "role": "employee",
    "department": { "id": 1, "name": "Разработка" },
    "daily_limit_kopecks": null,
    "is_active": true
  }
]
```

### `POST /api/admin/users`

```json
{
  "email": "new@kis.local",
  "password": "temporary",
  "full_name": "Новый Сотрудник",
  "role": "employee",
  "department_id": 1,
  "daily_limit_kopecks": null,
  "is_active": true
}
```

Ответ 201 — тот же объект, что в `GET /api/me` (без пароля).

### `PATCH /api/admin/users/{id}`

Любое подмножество: `role`, `department_id`, `daily_limit_kopecks`, `is_active`, `full_name`, `password`.

### `GET /api/admin/settings` / `PUT /api/admin/settings`

```json
{
  "cutoff_time": "16:00",
  "timezone": "Europe/Moscow",
  "mealty_city": "Москва",
  "daily_limit_kopecks": null,
  "catalog_sync_per_day": 2
}
```

`PUT` — полная замена этих ключей.

## Коды ошибок (договорённость)

| Код | Когда |
|-----|--------|
| 400 | невалидная дата, пустой состав при lock |
| 401 | нет/протух JWT |
| 403 | роль или cutoff |
| 404 | нет блюда / пользователя / отдела |
| 409 | конфликт статуса заказа |
| 429 | слишком частый sync Mealty |
| 502 | Mealty не ответил / HTML не распарсился |

## Версионирование

Пока один контракт без `/v1`. Ломающие поля — только через PR с пометкой в описании. Фронт не должен зависеть от порядка полей.
