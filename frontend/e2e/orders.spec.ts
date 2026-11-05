import { expect, test } from '@playwright/test';
import type { Order } from '../src/types';
import { money } from '../src/format';

test('summary loads people on demand, reports failed export and accepts repeated place', async ({
  page,
}, testInfo) => {
  let status: Order['status'] = 'collecting';
  let planReads = 0;
  let exports = 0;
  let places = 0;
  const order = (): Order => ({
    delivery_date: '2026-12-20',
    status,
    totals: {
      planned_kopecks: 123000,
      actual_kopecks: status === 'collecting' ? null : 127500,
      delta_kopecks: status === 'collecting' ? null : 4500,
      unavailable_count: 1,
    },
    items: [
      {
        dish_id: 1,
        external_id: '875',
        name: 'Ньокки',
        qty: 3,
        unit_price_kopecks: 42500,
        line_total_kopecks: 127500,
      },
    ],
    by_employee: [1, 2].map((id) => ({
      user_id: id,
      full_name: `Сотрудник ${id}`,
      department_id: null,
      department_name: null,
      actual_total_kopecks:
        status === 'collecting' ? null : id === 1 ? 85000 : 42500,
      unavailable_count: id === 1 ? 1 : 0,
    })),
  });
  await page.route('**/api/auth/login', (r) =>
    r.fulfill({ json: { access_token: 'contract-token' } }),
  );
  await page.route('**/api/me', (r) =>
    r.fulfill({
      json: {
        id: 3,
        email: 'procurement@test.local',
        full_name: 'Закупки',
        role: 'procurement',
        department: null,
        daily_limit_kopecks: null,
      },
    }),
  );
  await page.route('**/api/orders/*', (r) => r.fulfill({ json: order() }));
  await page.route('**/api/plans/*', (r) => {
    planReads++;
    return r.fulfill({
      json: {
        items: [
          {
            dish_id: 1,
            name: 'Ньокки',
            qty: 2,
            actual_price_kopecks: 42500,
            planned_price_kopecks: 41000,
            unavailable: false,
          },
          {
            dish_id: 2,
            name: 'Снятый салат',
            qty: 1,
            actual_price_kopecks: null,
            planned_price_kopecks: 20000,
            unavailable: true,
          },
        ],
      },
    });
  });
  await page.route('**/api/orders/*/cutoff', (r) => {
    expect(r.request().method()).toBe('POST');
    status = 'locked';
    return r.fulfill({
      json: {
        status,
        already_closed: false,
        sync: 'ok',
        plans_closed: 2,
        items_unavailable: 1,
      },
    });
  });
  await page.route('**/api/orders/*/export.csv', (r) => {
    exports++;
    return r.fulfill({ status: 500, json: { detail: 'Export failed' } });
  });
  await page.route('**/api/orders/*/place', (r) => {
    places++;
    expect(r.request().method()).toBe('POST');
    expect(r.request().headers().authorization).toBe('Bearer contract-token');
    status = 'placed';
    return r.fulfill({
      json: {
        status,
        already_placed: true,
        placed_at: '2026-12-19T12:00:00Z',
        placed_by_user_id: 4,
      },
    });
  });
  await page.goto('/orders');
  await page.getByLabel('Рабочая почта').fill('procurement@test.local');
  await page.getByLabel('Пароль', { exact: true }).fill('test');
  await page.getByRole('button', { name: 'Войти →' }).click();
  await expect(page.locator('.employee-row')).toHaveCount(2);
  expect(planReads).toBe(0);
  await expect(
    page
      .locator('.metrics > div')
      .filter({ hasText: 'Предварительная сумма' })
      .locator('strong'),
  ).toHaveText('—');
  await expect(
    page.getByRole('button', { name: 'Скачать список для заказа' }),
  ).toHaveCount(0);
  await page.locator('.employee-row summary').first().click();
  await expect(
    page.getByText('Нет в меню Mealty', { exact: true }),
  ).toBeVisible();
  expect(planReads).toBe(1);
  await page.getByRole('button', { name: 'Закрыть приём заказов' }).click();
  await page.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(page.locator('.order-toolbar .badge')).toContainText(
    'Приём закрыт',
  );
  await expect(page.getByRole('table')).toContainText(money(127500));
  await expect(page.getByRole('table')).not.toContainText('Снятый салат');
  await page.getByRole('button', { name: 'Скачать список для заказа' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(
    page.getByText('Список для заказа скачан.', { exact: true }),
  ).toHaveCount(0);
  expect(exports).toBe(1);
  await expect(page.locator('.order-toolbar .badge')).toContainText(
    'Приём закрыт',
  );
  await page
    .getByRole('button', { name: 'Заказ размещён', exact: true })
    .click();
  await page.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(
    page.getByText('Заказ уже размещён. Состав и сумма не изменились.'),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: '✓ Заказ размещён' }),
  ).toBeDisabled();
  expect(places).toBe(1);
  await page.reload();
  await expect(
    page.getByRole('button', { name: '✓ Заказ размещён' }),
  ).toBeDisabled();
  await expect(page.getByRole('table')).toContainText(money(127500));
  await expect(page.locator('.order-toolbar .badge')).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath('summary.png'),
    fullPage: true,
  });
});
