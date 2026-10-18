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
  "daily_limit_kopecks": null,
  "is_active": true
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

Если плана нет — пустой draft-шаблон без записи в БД: `id: null`, `items: []`, `editable` по cutoff.

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

403 `Forbidden` — роль не `employee` (закупки и админ). 403 `Cutoff passed` — дедлайн прошёл или статус уже не `draft`. 409 — блюдо не найдено или `unavailable`. 422 — `qty < 1`, повтор `dish_id`, или превышен дневной лимит.

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

Пока строки `office_orders` нет, тот же `GET` отдаёт живой вид, не 404: `status: "collecting"`, `by_employee` из draft-планов даты, `items` — предпросмотр по блюдам по текущей цене каталога. `totals.actual_kopecks`, `totals.delta_kopecks` и `by_employee[].actual_total_kopecks` — `null` (фактические цены ещё не зафиксированы). Запись в БД не создаётся.

```json
{
  "delivery_date": "2026-09-16",
  "status": "collecting",
  "totals": {
    "planned_kopecks": 82000,
    "actual_kopecks": null,
    "delta_kopecks": null,
    "unavailable_count": 0
  },
  "items": [
    {
      "dish_id": 12,
      "external_id": "875",
      "name": "Картофельные ньокки с грибами",
      "qty": 2,
      "unit_price_kopecks": 41000,
      "line_total_kopecks": 82000
    }
  ],
  "by_employee": [
    {
      "user_id": 1,
      "full_name": "Иван Сотрудник",
      "department_id": 1,
      "department_name": "Разработка",
      "actual_total_kopecks": null,
      "unavailable_count": 0
    }
  ]
}
```

`planned_kopecks`, `actual_kopecks` и `delta_kopecks` считаются только по позициям с `unavailable = false`; `delta_kopecks = actual_kopecks − planned_kopecks`. Недоступные позиции видны только через `unavailable_count` (в totals и в строке сотрудника). В `items` закрытого дня они не попадают: `items` — снимок `office_order_items` (имя и `external_id` — JOIN с `dishes`), `by_employee`, `planned_kopecks` и `unavailable_count` пересчитываются из `plan_items` планов `included_in_order`.

### `GET /api/orders/{date}/export.csv`

CSV: колонки `external_id, name, qty, unit_price_kopecks, line_total_kopecks`. UTF-8 с BOM (`utf-8-sig`), `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment`.

Переводит статус `locked → exported` (если ещё не placed). Если заказ уже `placed`, файл отдаётся, статус не откатывается.

403 `{"detail": "день ещё собирается"}`, если день ещё `collecting` (строки `office_orders` нет) — то же правило, что у `place`.

### `GET /api/orders/{date}/export.xlsx`

Тот же набор + лист «По сотрудникам». Те же правила статуса и 403 в collecting. `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

### `POST /api/orders/{date}/cutoff`

Ручное закрытие дня: тот же алгоритм, что у cutoff job, для указанной даты доставки (best-effort sync каталога → stamp `draft|locked → priced` → `office_order` в `locked` + планы `priced → included_in_order`). Нужен для демо, чтобы не ждать 16:00.

Доступ: закупки. Идемпотентно, если день уже `locked` / `exported` / `placed` (200 без изменений).

Ответ 200:

```json
{
  "delivery_date": "2026-10-14",
  "status": "locked",
  "already_closed": false,
  "sync": "ok",
  "plans_closed": 2,
  "items_unavailable": 1
}
```

Поля ответа:

- `sync`: `ok` — живой sync Mealty внутри cutoff прошёл; `skipped` — Mealty недоступен / HTML не распарсился / пустой снимок, либо день уже закрыт и нового похода не было. При `skipped` каталог не меняется, цены берутся из последнего сохранённого снимка.
- `plans_closed` — сколько планов переведено в `included_in_order` этим вызовом; при no-op — 0.
- `items_unavailable` — сколько позиций дня получили `unavailable = true`; при no-op — 0.

Квота: sync внутри cutoff — best-effort, пишет строку в `catalog_sync_runs` (честный учёт походов на Mealty), но не блокируется дневным лимитом; `429` остаётся поведением только ручного `POST /api/catalog/sync`.

400 `Empty day` — на дату нет ни одной позиции ни в одном плане (пустой состав при lock); job такой день молча пропускает.

Ручной cutoff разрешён и до естественного дедлайна (демо не ждёт 16:00); после закрытия правки `PUT /api/plans/{date}` запрещены по статусу (403 `Cutoff passed`).

### `POST /api/orders/{date}/place`

Тело необязательно. Ставит `placed`, пишет кто и когда.

403 `{"detail": "день ещё собирается"}`, если ещё `collecting` (cutoff не прошёл, строки `office_orders` нет). Идемпотентно, если уже `placed`: 200, первый `placed_at` и `placed_by_user_id` сохраняются.

Ответ 200:

```json
{
  "delivery_date": "2026-09-16",
  "status": "placed",
  "placed_at": "2026-09-15T13:05:00+00:00",
  "placed_by_user_id": 3,
  "already_placed": false
}
```

`already_placed: true` — повторный вызов; поля «кто и когда» остаются от первого размещения.

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

Хранение: одна строка `settings` (`id=1`). `PUT` — полная замена полей ниже. Только `admin`.

```json
{
  "cutoff_time": "16:00",
  "timezone": "Europe/Moscow",
  "mealty_city": "Москва",
  "daily_limit_kopecks": null,
  "catalog_sync_per_day": 2
}
```

`PUT` — полная замена этих ключей. `cutoff_time` — `HH:MM` (24h). Квота sync: ручной `POST /catalog/sync` и утренний job делят счётчик за календарные сутки в `timezone`; `sync-from-fixture` квоту не тратит.

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

Пока один контракт без `/v1`. Ломающие поля — только с согласия тимлида, в том же изменении, что и `docs/api.md`. Фронт не должен зависеть от порядка полей.
