import { expect, test } from '@playwright/test';
import type { Dish, Plan } from '../src/types';

// Requires seed-users and sync-from-fixture on the isolated test stack.
test('employee saves a real plan and reloads persisted quantities and prices', async ({
  page,
}, testInfo) => {
  await page.goto('/catalog');
  await page.getByLabel('Рабочая почта').fill('employee@kis.local');
  await page.getByLabel('Пароль', { exact: true }).fill('employee');
  const catalogResponse = page.waitForResponse(
    (r) => r.url().includes('/api/catalog?') && r.request().method() === 'GET',
  );
  const initialPlanResponse = page.waitForResponse(
    (r) => r.url().includes('/api/plans/') && r.request().method() === 'GET',
  );
  await page.getByRole('button', { name: 'Войти →' }).click();
  const catalog = await catalogResponse;
  expect(catalog.status()).toBe(200);
  const dishes: Dish[] = await catalog.json();
  const dish = dishes.find((item) => item.available);
  expect(dish, 'Run sync-from-fixture before this test').toBeDefined();
  if (!dish) throw new Error('The test catalog is empty');
  const initial = await initialPlanResponse;
  expect(initial.status()).toBe(200);
  const original: Plan = await initial.json();
  expect(original.editable).toBe(true);
  const previousQty =
    original.items.find((item) => item.dish_id === dish.id)?.qty ?? 0;
  try {
    await page
      .getByRole('button', { name: `Добавить ${dish.name}`, exact: true })
      .click();
    const savedResponse = page.waitForResponse(
      (r) => r.url().includes('/api/plans/') && r.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Сохранить план' }).click();
    const response = await savedResponse;
    expect(response.status()).toBe(200);
    const saved: Plan = await response.json();
    expect(saved.items.find((item) => item.dish_id === dish.id)).toMatchObject({
      qty: previousQty + 1,
      planned_price_kopecks: dish.price_kopecks,
    });
    expect(saved.planned_total_kopecks).toBe(
      saved.items.reduce(
        (sum, item) => sum + item.qty * item.planned_price_kopecks,
        0,
      ),
    );
    await expect(page.getByText('✓ План сохранён')).toBeVisible();
    // Let the save-triggered query refresh finish before observing the reload GET.
    await page.waitForLoadState('networkidle');
    const reloadResponse = page.waitForResponse(
      (r) => r.url().includes('/api/plans/') && r.request().method() === 'GET',
    );
    await page.reload();
    expect(await (await reloadResponse).json()).toEqual(saved);
    await expect(
      page.getByRole('button', { name: 'Сохранить план' }),
    ).toBeDisabled();
    await expect(
      page.locator('.plan-list').getByText(dish.name, { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath('plan-live.png'),
      fullPage: true,
    });
  } finally {
    const token = await page.evaluate(() =>
      localStorage.getItem('corplunch.access_token'),
    );
    const restored = await page.request.put(
      `/api/plans/${original.delivery_date}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          items: original.items.map(({ dish_id, qty }) => ({ dish_id, qty })),
        },
      },
    );
    expect(restored.status()).toBe(200);
  }
});
