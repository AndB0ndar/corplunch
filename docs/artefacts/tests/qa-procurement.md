# QA: закупки — сводка, выгрузки и размещение

Дата: **24.10.2026**. Версия: `c071b21` (включает backend `6368373`) + незакоммиченные frontend/QA-изменения этого задания. Проверяемая часть сценария [roles.md](../../roles.md): два сотрудника → сводка → cutoff → CSV/XLSX → ручная отметка размещения → повторный place.

**Результат: PASS в указанном объёме.** XLSX действительно открыт установленным Microsoft Excel 16.0; повторный place проверен на настоящем API от второго пользователя. Новых дефектов реализованной функциональности в этом прогоне не обнаружено.

## Окружение и метод

- Windows, установленный Edge (Chromium); desktop 1280×720 и мобильная эмуляция iPhone 13, 390×664. Мобильный прогон не является проверкой Safari или физического iPhone.
- Один корневой `docker-compose.yml` с `tests/.env.test`, проект `corplunch-tests`, API `18000`; Vite `5182`. Отдельного Compose в `qa/` нет. Серверные тесты используют отдельную базу `corplunch_test`.
- Live: настоящий вход, сохранение планов, sync, cutoff, сводка, файлы и place; HTTP-подмен нет. Планы двух новых сотрудников подготовлены через API, действия закупок выполнены браузером. После прогона учётки отключены; заказы оставлены в изолированной тестовой базе.
- Изолированный frontend-регресс отдельно проверяет HTTP-ошибку экспорта, снятое блюдо и сообщения cutoff с подменами API. Серверный регресс использует PostgreSQL и фикстуры/подмену провайдера без внешнего Mealty.
- Excel проверен автоматизацией отдельного скрытого экземпляра: XLSX открыт обычным способом только для чтения, без режима восстановления; CSV импортирован как UTF-8 с запятой. Проверены значения ячеек и типы чисел, не печатное оформление.

## Выполненный чек-лист

| Проверка | Результат и доказательство |
|---|---|
| Пустая дата: понятное состояние, закрытие недоступно | PASS, live desktop/mobile |
| Два сотрудника в collecting, составы раскрываются ниже таблицы | PASS, live; количества 2 + 1 |
| До расчёта фактическая сумма `null` отображается «—» | PASS, frontend HTTP-тест |
| Персональные планы загружаются только при раскрытии | PASS, frontend HTTP-тест считает запросы |
| Обновить каталог → `POST /api/catalog/sync` | PASS: desktop 200; mobile 429 и видимая ошибка квоты, сохранённый каталог доступен |
| Закрыть приём → подтверждение и `POST /api/orders/{date}/cutoff` | PASS, live 200, статус «Приём закрыт» |
| Доступные блюда агрегированы, суммы в UI — ₽ | PASS: 3 × 390 ₽ = 1 170 ₽, по сотрудникам 780 ₽ и 390 ₽ |
| Снятое блюдо не попадает в таблицу и сумму закупки | PASS в серверном `test_closed_day_aggregates_snapshot_and_live_people` и fixture-cutoff; предупреждение и исключение из UI-таблицы — frontend HTTP-тест. В live-каталоге снятие специально не моделировалось |
| CSV/XLSX скачаны через UI с именем выбранной даты | PASS, live desktop/mobile; файлы приложены ниже |
| XLSX открывается в Microsoft Excel, два листа, кириллица, количества, суммы | PASS, Excel 16.0, значения сверены с сохранённым ответом API; листы «Блюда» и «По сотрудникам» |
| CSV: BOM UTF-8, пять колонок, значения читаются Excel | PASS при импорте UTF-8/запятая. Открытие CSV двойным щелчком с региональным разделителем Windows не заявляется |
| День после выгрузки имеет статус exported | PASS, live, «Список выгружен» |
| Ошибка экспорта не выдаётся за успешное скачивание | PASS, frontend HTTP 500; видимая ошибка, статус сохранён |
| Повторный place безопасен | PASS: админ разместил заказ, затем закупки подтвердили ранее открытую форму; второй ответ 200, `already_placed=true`, прежние автор и время |
| После повторного place состав и суммы неизменны | PASS, полное сравнение сводки; повторная загрузка страницы показывает placed и отключённую кнопку |
| Экспорт после placed не откатывает статус | PASS, live GET XLSX 200, итоговый статус placed |
| Один статус, таблица выше аккордеонов, без редактирования чужих планов | PASS, просмотр desktop/mobile снимков; таблица на телефоне прокручивается внутри панели, горизонтального скролла страницы нет |

Выгрузки содержат целые **копейки**, как определено HTTP-контрактом; UI показывает рубли. Размещение на сайте Mealty остаётся ручным и в проверке не выполнялось.

## Результаты и доказательства

| Проверка | Итог | Доказательство |
|---|---|---|
| Lint, форматирование, TypeScript + Vite | PASS | [Сводка команд](qa-evidence/procurement-2026-10-24/checks.txt) |
| Unit | 33/33 | [JSON](qa-evidence/procurement-2026-10-24/unit-results.json) |
| Frontend E2E, desktop/mobile | 18/18 | [JSON](qa-evidence/procurement-2026-10-24/frontend-results.json) |
| Настоящий API закупок, desktop/mobile | 2/2 | [JSON](qa-evidence/procurement-2026-10-24/live-results.json) |
| Серверные summary, summary HTTP, cutoff, export render | 22/22 | [JUnit XML](qa-evidence/procurement-2026-10-24/backend.xml) |
| Excel: оба набора CSV/XLSX | PASS | [Desktop](qa-evidence/procurement-2026-10-24/desktop/excel-results.json), [mobile](qa-evidence/procurement-2026-10-24/mobile/excel-results.json) |

Файлы прогона (доставка 23.11.2026 на desktop и 24.11.2026 на mobile): [desktop XLSX](qa-evidence/procurement-2026-10-24/desktop/order.xlsx), [CSV](qa-evidence/procurement-2026-10-24/desktop/order.csv), [наблюдения](qa-evidence/procurement-2026-10-24/desktop/observations.json), [экран](qa-evidence/procurement-2026-10-24/desktop/summary-placed.png); [mobile XLSX](qa-evidence/procurement-2026-10-24/mobile/order.xlsx), [CSV](qa-evidence/procurement-2026-10-24/mobile/order.csv), [наблюдения](qa-evidence/procurement-2026-10-24/mobile/observations.json), [экран](qa-evidence/procurement-2026-10-24/mobile/summary-placed.png).

Повторение: [tests/README.md](../../../tests/README.md), конфиг `playwright.orders-live.config.ts` и скрипт `tests/check_excel_exports.ps1`. Live-проверки закупок могут обращаться к публичному Mealty и не входят в обычный CI. LibreOffice, Safari/Firefox и печать Excel в этом прогоне не проверялись.
