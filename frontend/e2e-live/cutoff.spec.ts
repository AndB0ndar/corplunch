import { expect, test } from '@playwright/test';
import type { Dish, Plan, Settings } from '../src/types';
import { shiftDate } from '../src/format';

// Changes real settings briefly: run alone, only on the isolated tests stack.
test('real cutoff preserves saved plan, locks an unsaved UI and rejects PUT', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(150000);
  const login = await request.post('/api/auth/login', {
    data: { email: 'admin@kis.local', password: 'admin' },
  });
  expect(login.status()).toBe(200);
  const { access_token } = await login.json();
  const headers = { Authorization: `Bearer ${access_token}` };
  const settingsResponse = await request.get('/api/admin/settings', {
    headers,
  });
  expect(settingsResponse.status()).toBe(200);
  const original: Settings = await settingsResponse.json();
  const email = `cutoff-${Date.now()}@qa.local`;
  const created = await request.post('/api/admin/users', {
    headers,
    data: {
      email,
      password: 'cutoff-test',
      full_name: 'QA cutoff',
      role: 'employee',
      department_id: null,
      daily_limit_kopecks: null,
      is_active: true,
    },
  });
  expect(created.status()).toBe(201);
  const user = await created.json();
  try {
    const serverNow = Date.parse(created.headers().date);
    expect(Number.isFinite(serverNow)).toBe(true);
    // Leave at least 30 seconds for the pre-cutoff save; HH:MM is the API contract.
    const deadline = Math.ceil((serverNow + 30000) / 60000) * 60000;
    const moscow = new Date(deadline + 3 * 3600000).toISOString();
    const cutoff_time = moscow.slice(11, 16);
    const deliveryDate = shiftDate(moscow.slice(0, 10), 1);
    const settings = await request.put('/api/admin/settings', {
      headers,
      data: {
        ...original,
        cutoff_time,
        timezone: 'Europe/Moscow',
        daily_limit_kopecks: null,
      },
    });
    expect(settings.status()).toBe(200);
    await page.goto('/catalog');
    await page.getByLabel('Рабочая почта').fill(email);
    await page.getByLabel('Пароль', { exact: true }).fill('cutoff-test');
    const menuResponse = page.waitForResponse((r) =>
      r.url().includes('/api/catalog?'),
    );
    await page.getByRole('button', { name: 'Войти →' }).click();
    const dishes: Dish[] = await (await menuResponse).json();
    const dish = dishes.find((d) => d.available);
    if (!dish)
      throw new Error('Seed the isolated catalog with sync-from-fixture');
    await page.getByLabel('Дата доставки').fill(deliveryDate);
    const add = page.getByRole('button', {
      name: `Добавить ${dish.name}`,
      exact: true,
    });
    await expect(add).toBeEnabled();
    await add.click();
    const savedResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/api/plans/${deliveryDate}`) &&
        r.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Сохранить план' }).click();
    const saved = await savedResponse;
    expect(saved.status()).toBe(200);
    const before: Plan = await saved.json();
    expect(before.editable).toBe(true);
    expect(before.items[0].qty).toBe(1);
    await expect(page.getByText('✓ План сохранён')).toBeVisible();
    await add.click();
    await expect(page.getByText('Есть несохранённые изменения')).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath('before-cutoff.png'),
      fullPage: true,
    });
    await expect(page.getByText('Приём закрыт', { exact: true })).toBeVisible({
      timeout: 105000,
    });
    await expect(add).toBeDisabled();
    await expect(
      page.getByRole('button', { name: `Увеличить ${dish.name}` }),
    ).toBeDisabled();
    await expect(
      page.getByRole('button', { name: 'Сохранить план' }),
    ).toHaveCount(0);
    await expect(page.getByText('Есть несохранённые изменения')).toHaveCount(0);
    await expect(
      page
        .getByRole('status')
        .filter({ hasText: 'Приём заказов на эту дату закрыт.' }),
    ).toHaveText(
      'Приём заказов на эту дату закрыт. Изменить состав уже нельзя.',
    );
    await expect(page.getByText(cutoff_time, { exact: false })).toHaveCount(0);
    const token = await page.evaluate(() =>
      localStorage.getItem('corplunch.access_token'),
    );
    const employeeHeaders = { Authorization: `Bearer ${token}` };
    const rejected = await request.put(`/api/plans/${deliveryDate}`, {
      headers: employeeHeaders,
      data: { items: [{ dish_id: dish.id, qty: 2 }] },
    });
    expect(rejected.status()).toBe(403);
    expect(await rejected.json()).toEqual({ detail: 'Cutoff passed' });
    const afterResponse = await request.get(`/api/plans/${deliveryDate}`, {
      headers: employeeHeaders,
    });
    expect(afterResponse.status()).toBe(200);
    const after: Plan = await afterResponse.json();
    expect(after.editable).toBe(false);
    expect(after.items).toEqual(before.items);
    await page.screenshot({
      path: testInfo.outputPath('after-cutoff.png'),
      fullPage: true,
    });
    await testInfo.attach('cutoff-observations', {
      contentType: 'application/json',
      body: JSON.stringify({
        deliveryDate,
        cutoff_time,
        timezone: 'Europe/Moscow',
        before: {
          http: 200,
          editable: before.editable,
          qty: before.items[0].qty,
        },
        after: {
          http: rejected.status(),
          editable: after.editable,
          qty: after.items[0].qty,
        },
        unsavedQty: 2,
        uiLocked: true,
      }),
    });
  } finally {
    const restored = await request.put('/api/admin/settings', {
      headers,
      data: original,
    });
    expect(restored.status()).toBe(200);
    const disabled = await request.patch(`/api/admin/users/${user.id}`, {
      headers,
      data: { is_active: false },
    });
    expect(disabled.ok()).toBe(true);
  }
});
