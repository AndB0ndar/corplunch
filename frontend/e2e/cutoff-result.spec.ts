import { expect, test } from '@playwright/test';
import type { CutoffResult, Order } from '../src/types';

const cases = [
  {
    name: 'updated',
    sync: 'ok',
    already_closed: false,
    message: 'Приём закрыт. Цены и наличие уточнены.',
  },
  {
    name: 'stored-snapshot',
    sync: 'skipped',
    already_closed: false,
    message:
      'Приём закрыт. Обновить меню Mealty не удалось — использованы последние сохранённые цены и наличие.',
  },
  {
    name: 'already-closed',
    sync: 'skipped',
    already_closed: true,
    message:
      'Приём уже закрыт. Состав заказа и зафиксированные цены не изменились.',
  },
] as const;

for (const scenario of cases) {
  test(`cutoff result: ${scenario.name}`, async ({ page }, testInfo) => {
    let closed = false;
    let calls = 0;
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        json: { access_token: 'contract-test', token_type: 'bearer' },
      }),
    );
    await page.route('**/api/me', (route) =>
      route.fulfill({
        json: {
          id: 3,
          email: 'procurement@qa.local',
          full_name: 'Закупки QA',
          role: 'procurement',
          department: null,
          daily_limit_kopecks: null,
        },
      }),
    );
    await page.route('**/api/orders/*', (route) => {
      const order: Order = {
        delivery_date: route.request().url().split('/').at(-1)!,
        status: closed ? 'locked' : 'collecting',
        totals: {
          planned_kopecks: 41000,
          actual_kopecks: 41000,
          delta_kopecks: 0,
          unavailable_count: 0,
        },
        items: [
          {
            dish_id: 1,
            external_id: '875',
            name: 'Ньокки',
            qty: 1,
            unit_price_kopecks: 41000,
            line_total_kopecks: 41000,
          },
        ],
        by_employee: [
          {
            user_id: 1,
            full_name: 'Сотрудник QA',
            department_id: null,
            department_name: null,
            actual_total_kopecks: 41000,
            unavailable_count: 0,
          },
        ],
      };
      return route.fulfill({ json: order });
    });
    await page.route('**/api/plans/*', (route) =>
      route.fulfill({ json: { items: [] } }),
    );
    await page.route('**/api/orders/*/cutoff', async (route) => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().headers().authorization).toBe(
        'Bearer contract-test',
      );
      calls++;
      closed = true;
      const result: CutoffResult = {
        delivery_date: route.request().url().split('/').at(-2)!,
        status: 'locked',
        already_closed: scenario.already_closed,
        sync: scenario.sync,
        plans_closed: scenario.already_closed ? 0 : 1,
        items_unavailable: 0,
      };
      await route.fulfill({ json: result });
    });
    await page.goto('/orders');
    await page.getByLabel('Рабочая почта').fill('procurement@qa.local');
    await page.getByLabel('Пароль', { exact: true }).fill('test');
    await page.getByRole('button', { name: 'Войти →' }).click();
    await page.getByRole('button', { name: 'Закрыть приём заказов' }).click();
    await expect(
      page.getByText('если Mealty недоступен', { exact: false }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Подтвердить' }).click();
    await expect(
      page.getByRole('status').filter({ hasText: scenario.message }),
    ).toBeVisible();
    if (scenario.name !== 'updated')
      await expect(
        page.getByText('Приём закрыт. Цены и наличие уточнены.', {
          exact: true,
        }),
      ).toHaveCount(0);
    if (scenario.name === 'already-closed')
      await expect(
        page.getByText(/Обновить меню Mealty не удалось/),
      ).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: 'Закрыть приём заказов' }),
    ).toHaveCount(0);
    expect(calls).toBe(1);
    await page.screenshot({
      path: testInfo.outputPath(`${scenario.name}.png`),
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Следующий день' }).click();
    await expect(page.getByText(scenario.message, { exact: true })).toHaveCount(
      0,
    );
  });
}
