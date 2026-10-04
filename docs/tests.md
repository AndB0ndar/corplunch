# Тесты

Карта проверок: где лежат, кто пишет, в каком этапе появляются.
Пункты задач — в [sprints.md](sprints.md).
Ручные чек-листы и прогоны — в [qa.md](qa.md).
Кейсы парсера Mealty — в [mealty.md](mealty.md).
DoD — в [process.md](process.md).

Проверка входит в тот же этап, что и поведение. Отдельной фазы «написать тесты» нет. CI не ходит на mealty.ru.

## Где

| Слой | Место | Кто |
|------|-------|-----|
| pytest | `backend/tests/` | автор модуля: Бондарь — ядро (`providers`, `catalog`, `planning`, `orders`, `stats`, jobs); Пягай — auth, admin, хелперы 422/429, контракт ролей и cutoff, рендер CSV/XLSX |
| HTML-фикстура | `backend/tests/fixtures/mealty_catalog.html` | файл кладёт Шишков, регресс селекторов — Бондарь |
| Vitest | `frontend/src/**/*.test.ts`, `frontend/src/**/*.test.tsx` | Шишков |
| Playwright | `frontend/e2e/`, `frontend/e2e-live/` | Шишков |
| Ручной регресс | [qa.md](qa.md), прогоны в `docs/artefacts/tests/` | Шишков |

Общий каркас pytest — `backend/tests/conftest.py`: база `corplunch_test`, сброс схемы, анонимный клиент. Фикстуры Bearer для employee / procurement / admin — открытый пункт этапа 2; до них логин не копировать в каждый файл.

Сейчас в `backend/tests/`: health, OpenAPI, Alembic, auth, users, departments, settings, квота, парсер, upsert каталога, HTTP каталога, job sync, планы. Файлов на cutoff-job, сводку, экспорт и stats ещё нет — их пункты в этапах 2–4.

## Когда

| Этап | Что появляется вместе с фичей |
|------|--------------------------------|
| 0 | образец pytest отделов и health, CI, структура auth; чек-лист входа |
| 1 | регресс парсера на фикстуре, upsert, HTTP каталога, job sync, квота 429, settings |
| 2 | контракт ролей и cutoff, Bearer трёх ролей, CSV/XLSX на фикстуре DTO, QA cutoff |
| 3 | pytest сводки, идемпотентный `place`, экспорт `locked → exported`; чек-лист закупок |
| 4 | pytest `GET /api/stats/summary`; дыры auth/admin; полный регресс по [demo.md](demo.md) |

Пягай пишет pytest cutoff параллельно с job Бондаря. Шишков закрывает чек-лист до обзора этапа. Приёмка демо на этапе 4 не заменяет pytest статистики.

## Команды

```bash
docker compose exec api pytest
```

Фронтенд: `npm test` и `npm run test:e2e` — как в [frontend.md](frontend.md). CI: `.github/workflows/ci.yml`, два job. Backend-база в CI — `corplunch_test`.

## Инварианты

- Деньги в проверках — целые копейки.
- Селекторы Mealty меняются только вместе с регрессом на HTML-фикстуре.
- 5xx и пустой каталог — ошибка сети. Тест не ждёт массового `unavailable`.
- Живой mealty.ru в CI не вызывать. Ручной `pytest -m live` — вне CI, см. [mealty.md](mealty.md).
