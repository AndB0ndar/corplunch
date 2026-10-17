# Модель данных

Цены храним в копейках (`integer`), чтобы не ловить ошибки float. HTTP API использует те же имена полей (`*_kopecks`) — см. [api.md](api.md). Даты планов — календарные `date` в часовом поясе офиса (`Europe/Moscow`).

## ER-обзор

```mermaid
erDiagram
  departments ||--o{ users : has
  users ||--o{ meal_plans : creates
  meal_plans ||--o{ plan_items : contains
  dishes ||--o{ plan_items : chosen
  dishes ||--o{ price_history : tracked
  dishes ||--o{ office_order_items : aggregated
  office_orders ||--o{ office_order_items : contains
  office_orders ||--o{ meal_plans : locks
```

## Таблицы

### `departments`

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | |
| name | str | «Разработка», «Закупки», … |

Нужны для статистики расхода, не для ACL.

### `users`

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | |
| email | unique | логин |
| password_hash | str | |
| full_name | str | |
| role | enum | `employee`, `procurement`, `admin` |
| department_id | FK nullable | |
| daily_limit_kopecks | int nullable | персональный лимит; иначе системный |
| is_active | bool | |

### `settings` (одна строка, singleton `id=1`)

Хранение — одна строка таблицы `settings` (не key-value). Дефолты сидятся миграцией `0004_settings`. Счётчик живых sync Mealty — таблица `catalog_sync_runs` (`ran_at`); лимит за календарные сутки в `settings.timezone`.

| Ключ | Значение по умолчанию | Смысл |
|------|----------------------|--------|
| `cutoff_time` | `16:00` | до какого времени правится план на завтра |
| `timezone` | `Europe/Moscow` | |
| `mealty_city` | `Москва` | влияет на цены парсера |
| `daily_limit_kopecks` | null | общий лимит ₽/сотрудник/день, опционально |
| `catalog_sync_per_day` | `2` | мягкий лимит запросов к Mealty |

### `catalog_sync_runs`

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | |
| ran_at | timestamptz | момент, когда sync прошёл квоту и пошёл на Mealty |

Cutoff-sync (job закрытия дня и ручной `POST /api/orders/{date}/cutoff`) тоже пишет строку до похода на Mealty, но не блокируется лимитом `catalog_sync_per_day`: день обязан закрыться всегда; счётчик учитывает его для последующих `429`.

### `dishes`

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | внутренний |
| source | str | `mealty` |
| external_id | str | `data-product_id` |
| seller_product_id | str nullable | `data-seller-product_id` |
| name | str | |
| subtitle | str | `.meal-card__name-note` |
| category | str | `breakfast`, `salad`, … |
| price_kopecks | int | последняя известная цена |
| old_price_kopecks | int nullable | |
| weight_g | int nullable | |
| proteins, fats, carbs, calories | numeric nullable | |
| image_url | str nullable | |
| description | text nullable | |
| available | bool | есть в последнем sync |
| unique | (source, external_id) | |

### `price_history`

Снимок при каждом успешном sync.

| Поле | Тип |
|------|-----|
| id | PK |
| dish_id | FK |
| price_kopecks | int |
| recorded_at | timestamptz |

Нужна для графиков и отчёта «план vs факт».

### `meal_plans`

Один план = один сотрудник × одна дата доставки.

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | |
| user_id | FK | |
| delivery_date | date | |
| status | enum | см. ниже |
| office_order_id | FK nullable | после сборки дня |
| unique | (user_id, delivery_date) | |

Статусы плана (enum в коде, цепочка контракта):

```
draft → locked → priced → included_in_order
```

| Статус | Когда |
|--------|--------|
| `draft` | можно редактировать, пока дедлайн не прошёл и статус ещё `draft` |
| `locked` | промежуточный «правки закрыты, цены ещё не проставлены»; stamp принимает `draft` и `locked` |
| `priced` | проставлены `actual_price_kopecks` / `unavailable` (`apply_actual_prices`) |
| `included_in_order` | вошёл в сводный `office_order` (финал cutoff) |

Алгоритм cutoff (job и `POST /api/orders/{date}/cutoff`) в одном проходе: проверка идемпотентности → best-effort sync каталога → `draft|locked → priced` → создать `office_order` в `locked` и агрегат позиций с `unavailable=false` → `priced → included_in_order`. На happy path план обычно не останавливается в `locked`: `draft → priced → included_in_order`.

### `plan_items`

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | |
| plan_id | FK | |
| dish_id | FK | |
| qty | int ≥ 1 | |
| planned_price_kopecks | int | копия `dishes.price_kopecks` на момент успешного `PUT` |
| actual_price_kopecks | int nullable | цена после cutoff |
| unavailable | bool | блюда не было в свежем каталоге |

В сводку закупок позиция попадает, только если `unavailable = false`.

### `office_orders`

Сводный заказ офиса на дату доставки.

| Поле | Тип | Описание |
|------|-----|----------|
| id | PK | |
| delivery_date | date unique | |
| status | enum | см. ниже |
| placed_at | timestamptz nullable | |
| placed_by_user_id | FK nullable | |

Статусы сводного заказа (enum в коде):

```
collecting → locked → exported → placed
```

| Статус | Когда |
|--------|--------|
| `collecting` | концептуально «до cutoff»; строка `office_orders` на дату ещё не создана (или зарезервировано под контракт `place` на этапе 3) |
| `locked` | день закрыт cutoff: строка появляется сразу в `locked` с снимком позиций |
| `exported` | хотя бы раз скачали CSV/XLSX (ставит роутер экспорта на этапе 3) |
| `placed` | закупки подтвердили размещение на Mealty (`POST …/place`, этап 3) |

Идемпотентность cutoff: если на дату уже есть `office_order` в любом статусе (`locked` / `exported` / `placed`) — повторный вызов возвращает 200 без изменений (`already_closed=true`, без нового sync).

### `office_order_items`

Агрегат по блюду (не по человеку). Персональная разбивка считается из `plan_items`.

| Поле | Тип |
|------|-----|
| office_order_id | FK |
| dish_id | FK |
| qty | int |
| unit_price_kopecks | int (actual) |
| line_total_kopecks | int |

## Правило цены

Как в коде (`replace_plan` + `apply_actual_prices`):

1. Пока план `draft`, UI ориентируется на `dishes.price_kopecks` (последний sync). Успешный `PUT /plans` копирует текущую `dishes.price_kopecks` в `planned_price_kopecks` позиции.
2. Cutoff вызывает `apply_actual_prices` для планов в `draft` или `locked`: если блюдо `available` — `actual_price_kopecks = dishes.price_kopecks`, `unavailable=false`; иначе `actual_price_kopecks=null`, `unavailable=true`. Затем план → `priced`.
3. В снимок `office_order_items` и суммы закупок входят только позиции с `unavailable=false` (и непустым `actual_price_kopecks`).
4. Дельта для статистики: `actual_price_kopecks * qty − planned_price_kopecks * qty` (unavailable считают отдельно: «не закуплено»).

## Индексы

- `dishes (source, external_id)` unique
- `meal_plans (user_id, delivery_date)` unique
- `meal_plans (delivery_date, status)`
- `plan_items (plan_id, dish_id)` unique
- `price_history (dish_id, recorded_at)`
- `office_orders (delivery_date)` unique
