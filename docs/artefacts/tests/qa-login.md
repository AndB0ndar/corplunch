# QA: вход трёх ролей и четырёх учётных записей

**Прогон:** 29.09.2026, 17:24:42–17:25:00 Europe/Moscow. **Версия приложения:** `4639c7e`; добавленный QA-набор — в этой же поставке. **Результат авторизации:** PASS, 11/11 проверок, без повторных попыток тестов. **Область проверки:** реализованные вход, профиль, навигация по ролям, сессия и защита API.

Это выполненный автоматизированный браузерный прогон обычной формы входа и HTTP-проверки настоящего API. Использованы Windows, Microsoft Edge 153.0.4234.48, Playwright, viewport 1280×720, Vite, FastAPI в Python 3.12 и PostgreSQL 16. Скриншоты показывают сообщение о неверном пароле и шапку с именем, ролью и навигацией после успешного входа. Мобильный live-прогон в эту проверку не входит.

Стандартный `seed-users` создал четыре тестовые учётные записи в отдельной базе `corplunch-login-qa`. Использовались пароли из README. Кнопки деморежима не нажимались; подмен API, JWT и зависимостей backend не было. В каждом браузерном тесте создавался новый контекст. Запросы к Mealty не выполнялись.

## Выполненный чек-лист

| ID | Действия | Ожидаемый результат | Факт |
|---|---|---|---|
| LOGIN-01 | Войти через почту и пароль `employee@kis.local` | `POST /api/auth/login` 200; `/api/me` 200; employee; `/catalog` | PASS, id=1; шапка «Иван Сотрудник / Сотрудник» |
| LOGIN-02 | Войти как `employee2@kis.local` | Отдельная учётная запись employee; `/catalog` | PASS, id=2; «Пётр Сотрудник / Сотрудник» |
| LOGIN-03 | Войти как `procurement@kis.local` | procurement; `/orders`; ссылки сводки и статистики | PASS, id=3; «Анна Закупки / Закупки» |
| LOGIN-04 | Войти как `admin@kis.local` | admin; `/orders`; дополнительно доступно «Управление» | PASS, id=4; «Администратор»; переход `/admin` разрешён |
| LOGIN-05 | Для каждой из четырёх записей сначала отправить неверный пароль, затем верный | 401, видимая ошибка, токен не сохраняется; повторный вход успешен | PASS для всех четырёх; сообщение «Сессия завершена или неверная почта / пароль. Войдите снова.» |
| LOGIN-06 | Проверить запрос `/api/me` после входа | Заголовок Bearer, без Cookie; профиль без password_hash | PASS для всех четырёх |
| LOGIN-07 | После входа проверить localStorage | Сохраняется ключ токена, пароль не сохраняется | PASS: единственный ключ `corplunch.access_token` |
| LOGIN-08 | Перезагрузить страницу после входа | Сессия сохраняется; `/api/me` 200, прежнее имя в шапке | PASS для всех четырёх |
| LOGIN-09 | Открыть `/admin`, `/orders`, `/stats` сотрудником; `/admin` закупками | Возврат на разрешённый домашний экран | PASS для обоих сотрудников и закупок |
| LOGIN-10 | Вызвать `/api/admin/users` с настоящими токенами всех четырёх записей | 403 для employee/employee2/procurement; 200 для admin | PASS |
| LOGIN-11 | Вызвать `POST /api/catalog/sync` каждым сотрудником | 403 до обращения к Mealty | PASS для employee и employee2 |
| LOGIN-12 | Получить `/api/me` токенами двух сотрудников | Разные id, соответствующие адреса и одинаковая роль employee | PASS: id=1 и id=2 |
| LOGIN-13 | Нажать «Выйти», затем перезагрузить страницу | Токен удалён, показана форма входа | PASS для всех четырёх |
| LOGIN-14 | Отправить заведомо некорректный Bearer | 401, `{"detail":"Invalid token"}` | PASS |

### Защищённые методы без токена

Запросы выполнялись отдельным HTTP-контекстом без браузерного токена. Во всех пяти случаях получены **401**, `WWW-Authenticate: Bearer`, `{"detail":"Not authenticated"}`.

| Метод | Путь | Результат |
|---|---|---|
| GET | `/api/me` | PASS |
| GET | `/api/catalog` | PASS |
| POST | `/api/catalog/sync` | PASS |
| GET | `/api/admin/users` | PASS |
| GET | `/api/admin/departments` | PASS |

`/api/health` и `/api/auth/login` по контракту доступны без токена. Истечение JWT и отключение пользователя этим набором не проверялись.

## Ошибки в проверенной функциональности

Ошибок не обнаружено. Ответы 401 при неверном пароле или отсутствии токена и 403 при недостаточных правах соответствуют ожидаемому поведению.

## Доказательства

- [Результаты 11 проверок авторизации](qa-evidence/login-2026-09-29/results.json).
- Скриншоты: [employee](qa-evidence/login-2026-09-29/employee-login.png), [employee2](qa-evidence/login-2026-09-29/employee2-login.png), [procurement](qa-evidence/login-2026-09-29/procurement-login.png), [admin](qa-evidence/login-2026-09-29/admin-login.png), [неверный пароль](qa-evidence/login-2026-09-29/wrong-password.png).
- [Исполняемые проверки](../../../frontend/e2e-live/login.spec.ts) и [отдельная конфигурация](../../../frontend/playwright.live.config.ts).

В опубликованных доказательствах нет JWT и введённых паролей; адреса и имена принадлежат штатным тестовым пользователям. Запись Playwright trace выключена, поскольку trace может содержать Authorization.

## Повторение прогона

Нужны запущенный Docker Desktop, Node/npm и Microsoft Edge. Из корня проекта:

```powershell
docker compose -f qa/login.compose.yml up -d --build
docker compose -f qa/login.compose.yml exec -T api python -m app.cli seed-users
```

В первом терминале запустить frontend:

```powershell
cd frontend
npm ci
$env:API_PROXY_TARGET = 'http://127.0.0.1:18000'
npm run dev -- --host 127.0.0.1 --port 5181 --strictPort
```

Во втором терминале из корня проекта проверить готовность API, затем запустить тесты:

```powershell
Invoke-RestMethod http://127.0.0.1:5181/api/health
cd frontend
$env:PLAYWRIGHT_CHANNEL = 'msedge'
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:5181'
npx playwright test --config=playwright.live.config.ts
```

Health должен показать `status=ok`, `database=up`. Новый JSON-отчёт появится в `.qa/login-results.json`, скриншоты — в `frontend/test-results/live-login/`; эти рабочие результаты исключены из Git. Сохранённые доказательства выше относятся только к прогону 29.09.2026. Для Chromium нужно установить его через Playwright и не задавать `PLAYWRIGHT_CHANNEL`.

После проверки остановить Vite через Ctrl+C и из корня выполнить:

```powershell
docker compose -f qa/login.compose.yml stop
```

QA Compose использует отдельный проект и базу, фиксированные учебные секреты и API только на `127.0.0.1:18000`; он не предназначен для развёртывания сервиса. Запуск через `sh -c` применяет штатные миграции и запускает `app.main:app`, избегая зависимости от Windows-переносов строк в shell-файле. Это не полная приёмка основного `docker-compose.yml`.

