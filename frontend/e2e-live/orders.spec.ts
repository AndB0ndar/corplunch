import { expect, test, type APIRequestContext } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { unzipSync, strFromU8 } from 'fflate';
import { money, shiftDate, today } from '../src/format';
import type { Dish, Order, PlaceResult, User } from '../src/types';

// Explicit live test on the isolated stack. Sync/cutoff may fetch public Mealty.
// No HTTP mocks. Test accounts are disabled afterwards; the placed order remains.
test('two employees, real summary, CSV/XLSX and idempotent place', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(180000);
  async function login(
    client: APIRequestContext,
    account: string,
    password: string,
  ) {
    const response = await client.post('/api/auth/login', {
      data: { email: account, password },
    });
    expect(response.status()).toBe(200);
    return { Authorization: `Bearer ${(await response.json()).access_token}` };
  }
  const adminHeaders = await login(request, 'admin@kis.local', 'admin');
  const procurementHeaders = await login(
    request,
    'procurement@kis.local',
    'procurement',
  );
  const users: User[] = [];
  let date = shiftDate(today(), 30);
  for (let offset = 30; offset < 90; offset++) {
    date = shiftDate(today(), offset);
    const response = await request.get(`/api/orders/${date}`, {
      headers: procurementHeaders,
    });
    expect(response.status()).toBe(200);
    const candidate: Order = await response.json();
    if (candidate.status === 'collecting' && candidate.by_employee.length === 0)
      break;
    if (offset === 89) throw new Error('No empty test date');
  }
  const orderPath = `/api/orders/${date}`;
  try {
    await page.goto('/orders');
    await page.getByLabel('Рабочая почта').fill('procurement@kis.local');
    await page.getByLabel('Пароль', { exact: true }).fill('procurement');
    await page.getByRole('button', { name: 'Войти →' }).click();
    await page.getByLabel('Дата доставки').fill(date);
    await expect(page.locator('.order-toolbar .badge')).toContainText(
      'Собираем планы',
    );
    await expect(
      page.getByRole('button', { name: 'Закрыть приём заказов' }),
    ).toBeDisabled();
    const syncResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/catalog/sync') &&
        r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Обновить каталог' }).click();
    const synced = await syncResponse;
    expect([200, 429, 502]).toContain(synced.status());
    if (synced.status() !== 200)
      await expect(page.getByRole('alert')).toBeVisible();
    const catalog = await request.get('/api/catalog?available_only=true', {
      headers: procurementHeaders,
    });
    expect(catalog.status()).toBe(200);
    const dishes: Dish[] = await catalog.json();
    const dish = dishes.find((d) => d.available);
    if (!dish) throw new Error('Seed or sync an available test catalog first');
    const run = Date.now();
    for (const index of [1, 2]) {
      const email = `orders-${run}-${index}@qa.local`;
      const response = await request.post('/api/admin/users', {
        headers: adminHeaders,
        data: {
          email,
          password: 'orders-test',
          full_name: `QA Закупки ${index} ${run}`,
          role: 'employee',
          department_id: null,
          daily_limit_kopecks: 10000000,
          is_active: true,
        },
      });
      expect(response.status()).toBe(201);
      users.push(await response.json());
      const headers = await login(request, email, 'orders-test');
      const saved = await request.put(`/api/plans/${date}`, {
        headers,
        data: { items: [{ dish_id: dish.id, qty: index === 1 ? 2 : 1 }] },
      });
      expect(saved.status()).toBe(200);
    }
    await page.reload();
    await page.getByLabel('Дата доставки').fill(date);
    await expect(page.locator('.employee-row')).toHaveCount(2);
    for (const user of users) {
      const row = page
        .locator('.employee-row')
        .filter({ hasText: user.full_name });
      await row.locator('summary').click();
      await expect(row.locator('.read-plan-row')).toContainText(dish.name);
    }
    const closing = page.waitForResponse(
      (r) =>
        r.url().endsWith(`${orderPath}/cutoff`) &&
        r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Закрыть приём заказов' }).click();
    await page.getByRole('button', { name: 'Подтвердить' }).click();
    expect((await closing).status()).toBe(200);
    await expect(page.locator('.order-toolbar .badge')).toContainText(
      'Приём закрыт',
    );
    const summaryResponse = await request.get(orderPath, {
      headers: procurementHeaders,
    });
    expect(summaryResponse.status()).toBe(200);
    const summary: Order = await summaryResponse.json();
    expect(summary.by_employee).toHaveLength(2);
    expect(
      summary.items.length,
      'Live catalog must still contain the selected dish for the file-opening scenario',
    ).toBeGreaterThan(0);
    expect(summary.items[0].qty).toBe(3);
    expect(summary.totals.actual_kopecks).toBe(
      summary.items.reduce((sum, item) => sum + item.line_total_kopecks, 0),
    );
    await expect(page.getByRole('table')).toContainText(
      money(summary.items[0].line_total_kopecks),
    );
    for (const format of ['csv', 'xlsx'] as const) {
      const downloadEvent = page.waitForEvent('download');
      await page
        .getByRole('button', {
          name:
            format === 'csv' ? 'Скачать список для заказа' : 'Скачать Excel',
        })
        .click();
      const file = await downloadEvent;
      expect(file.suggestedFilename()).toBe(`corplunch-${date}.${format}`);
      const path = testInfo.outputPath(`order.${format}`);
      await file.saveAs(path);
      expect(await file.failure()).toBeNull();
      const bytes = await readFile(path);
      if (format === 'csv') {
        expect(bytes.subarray(0, 3)).toEqual(Buffer.from([0xef, 0xbb, 0xbf]));
        expect(bytes.toString('utf8')).toContain(
          'external_id,name,qty,unit_price_kopecks,line_total_kopecks',
        );
        expect(bytes.toString('utf8')).toContain(summary.items[0].name);
      } else {
        const zip = unzipSync(bytes);
        const workbook = strFromU8(zip['xl/workbook.xml']);
        expect(workbook).toContain('Блюда');
        expect(workbook).toContain('По сотрудникам');
        expect(strFromU8(zip['xl/worksheets/sheet1.xml'])).toContain(
          `<v>${summary.items[0].line_total_kopecks}</v>`,
        );
      }
    }
    await expect(page.locator('.order-toolbar .badge')).toContainText(
      'Список выгружен',
    );
    // Another procurement-capable actor places while this user's confirmation is open.
    await page
      .getByRole('button', { name: 'Заказ размещён', exact: true })
      .click();
    const first = await request.post(`${orderPath}/place`, {
      headers: adminHeaders,
    });
    expect(first.status()).toBe(200);
    const firstBody: PlaceResult = await first.json();
    expect(firstBody.already_placed).toBe(false);
    const repeatResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith(`${orderPath}/place`) &&
        r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Подтвердить' }).click();
    const repeat = await repeatResponse;
    expect(repeat.status()).toBe(200);
    expect(await repeat.json()).toEqual({ ...firstBody, already_placed: true });
    await expect(
      page.getByText('Заказ уже размещён. Состав и сумма не изменились.'),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: '✓ Заказ размещён' }),
    ).toBeDisabled();
    const exportedAfter = await request.get(`${orderPath}/export.xlsx`, {
      headers: procurementHeaders,
    });
    expect(exportedAfter.status()).toBe(200);
    const final = await request.get(orderPath, { headers: procurementHeaders });
    expect(await final.json()).toEqual({ ...summary, status: 'placed' });
    await page.reload();
    await page.getByLabel('Дата доставки').fill(date);
    await expect(
      page.getByRole('button', { name: '✓ Заказ размещён' }),
    ).toBeDisabled();
    await expect(page.getByRole('table')).toContainText(
      money(summary.items[0].line_total_kopecks),
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath('summary-placed.png'),
      fullPage: true,
    });
    await testInfo.attach('observations', {
      body: JSON.stringify({
        date,
        sync_http: synced.status(),
        summary,
        first_place: firstBody,
        repeated_place: true,
        export_after_placed: true,
      }),
      contentType: 'application/json',
    });
  } finally {
    for (const user of users) {
      const disabled = await request.patch(`/api/admin/users/${user.id}`, {
        headers: adminHeaders,
        data: { is_active: false },
      });
      expect(disabled.status()).toBe(200);
    }
  }
});
