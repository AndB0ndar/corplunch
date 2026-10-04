# Тестовый стенд

Используется корневой `docker-compose.yml`. Отличия от обычного запуска заданы в `.env.test`: имя проекта `corplunch-tests`, локальные порты и учебное окружение API. Второго Compose нет. `.env.test` содержит только публичные тестовые значения и хранится в Git; настоящие секреты сюда не добавлять.

Имя проекта отделяет контейнеры, сеть и тома PostgreSQL от обычного приложения. Использовать команды ниже из корня репозитория. Не подменять имя проекта через `-p` и не запускать разрушающие тесты на общей базе.

## Браузерные проверки с настоящим API

```powershell
docker compose --env-file tests/.env.test up -d --build db api
docker compose --env-file tests/.env.test exec -T api python -m app.cli seed-users
docker compose --env-file tests/.env.test exec -T api python -m app.cli sync-from-fixture
```

API: `http://127.0.0.1:18000`; PostgreSQL: `127.0.0.1:15432`. Штатный entrypoint применяет миграции и запускает API. `.gitattributes` сохраняет LF в entrypoint при checkout на Windows.

В первом терминале:

```powershell
Set-Location frontend
npm ci
$env:API_PROXY_TARGET='http://127.0.0.1:18000'
npm run dev -- --host 127.0.0.1 --port 5181 --strictPort
```

Во втором терминале:

```powershell
Set-Location frontend
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:5181'
$env:PLAYWRIGHT_CHANNEL='msedge'
npx playwright test --config=playwright.live.config.ts
npx playwright test --config=playwright.admin-live.config.ts
npx playwright test --config=playwright.plans-live.config.ts
```

JSON-результаты — `tests/results/` (игнорируются Git), скриншоты — `frontend/test-results/`. Для Chromium вместо установленного Edge выполнить `npx playwright install chromium` и убрать `PLAYWRIGHT_CHANNEL`. Демонстрационные пользователи и пароли — в корневом README. Live-сценарии создают тестовых сотрудников/отделы; настройки после проверки восстанавливаются.

Проверка плана использует каталог из локальной HTML-фикстуры, сохраняет блюдо через UI и проверяет состав/цены после перезагрузки. Исходный состав восстанавливается через API. `sync-from-fixture` не обращается к Mealty.

Если нужен web в Docker, запустить `docker compose --env-file tests/.env.test up -d --build web`. Адрес — `http://127.0.0.1:15173`; для Playwright задать этот `PLAYWRIGHT_BASE_URL` вместо 5181.

## Серверные проверки

Тесты исключены из runtime-образа. Для запуска в тестовом контейнере скопировать содержимое каталога, включая точку после `tests/`, чтобы не создать вложенный `tests/tests`:

```powershell
docker compose --env-file tests/.env.test cp backend/tests/. api:/app/tests
docker compose --env-file tests/.env.test exec -T api pip install -r requirements-dev.txt
docker compose --env-file tests/.env.test exec -T api python -m pytest -q
```

Pytest использует отдельную базу `corplunch_test` в тестовом PostgreSQL и пересоздаёт её таблицы. Это не база приложения `corplunch`.

## Какие проверки используют моки

- Изолированные frontend-тесты подменяют API; браузерные сценарии обработки ошибок используют HTTP-подмены.
- Серверные тесты каталога используют HTML-фикстуры и подмену внешнего провайдера, без запросов к Mealty.
- Интеграционные тесты auth/users/settings, миграций и upsert используют PostgreSQL. В проекте есть `sqlalchemy.dialects.postgresql.insert`, asyncpg и проверки `pg_catalog`; SQLite не заменяет эти проверки. Мок сессии тоже не проверяет миграции и фактическое сохранение.

После работы остановить Vite через Ctrl+C и выполнить:

```powershell
docker compose --env-file tests/.env.test stop
```

Тома с тестовыми данными сохраняются. При переходе со старого стенда сначала остановить его контейнеры `corplunch-login-qa-api-1` и `corplunch-login-qa-db-1`, если они ещё запущены: старый API также занимал порт 18000. Исторические доказательства в `docs/artefacts/tests/` описывают окружение соответствующего прогона.
