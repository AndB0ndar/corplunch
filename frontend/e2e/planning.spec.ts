import { expect, test } from '@playwright/test';
import type { Dish, Plan } from '../src/types';
import { money } from '../src/format';

const dishes: Dish[] = ['Суп', 'Салат', 'Пирог'].map((name, index) => ({
  id: index + 1,
  name,
  source: 'mealty',
  external_id: String(index + 1),
  seller_product_id: null,
  subtitle: '',
  description: null,
  category: 'main_dish',
  price_kopecks: 20000,
  old_price_kopecks: null,
  weight_g: null,
  proteins: null,
  fats: null,
  carbs: null,
  calories: null,
  image_url: null,
  available: true,
}));

test('calendar, dirty polling, closed mobile plan and price directions', async ({
  page,
}, testInfo) => {
  test.setTimeout(45000);
  let closed = false;
  let priced = false;
  let reads = 0;
  await page.route('**/api/auth/login', (route) =>
    route.fulfill({
      json: { access_token: 'contract-token', token_type: 'bearer' },
    }),
  );
  await page.route('**/api/me', (route) =>
    route.fulfill({
      json: {
        id: 1,
        email: 'employee@test.local',
        full_name: 'Сотрудник QA',
        role: 'employee',
        department: null,
        daily_limit_kopecks: null,
      },
    }),
  );
  await page.route('**/api/catalog?*', (route) =>
    route.fulfill({ json: dishes }),
  );
  await page.route('**/api/plans/*', (route) => {
    reads++;
    const plan: Plan = {
      id: 1,
      user_id: 1,
      delivery_date: route.request().url().split('/').at(-1)!,
      editable: !closed,
      status: priced ? 'priced' : 'draft',
      planned_total_kopecks: priced ? 60000 : 20000,
      actual_total_kopecks: priced ? 40000 : null,
      items: (priced ? dishes : dishes.slice(0, 1)).map((dish, index) => ({
        dish_id: dish.id,
        name: dish.name,
        qty: 1,
        planned_price_kopecks: 20000,
        actual_price_kopecks:
          priced && index < 2 ? [25000, 15000][index] : null,
        unavailable: priced && index === 2,
      })),
    };
    return route.fulfill({ json: plan });
  });
  await page.goto('/catalog');
  await page.getByLabel('Рабочая почта').fill('employee@test.local');
  await page.getByLabel('Пароль', { exact: true }).fill('test');
  await page.getByRole('button', { name: 'Войти →' }).click();
  const total = page.getByLabel('Сумма плана');
  await expect(total).toContainText(money(20000));
  await page.getByLabel('Дата доставки').fill('2026-12-31');
  await page.getByRole('button', { name: 'Следующий день' }).click();
  await expect(page.getByLabel('Дата доставки')).toHaveValue('2027-01-01');
  await page.getByRole('button', { name: 'Предыдущий день' }).click();
  await expect(page.getByLabel('Дата доставки')).toHaveValue('2026-12-31');
  await page.getByRole('button', { name: 'Добавить Суп', exact: true }).click();
  await expect(total).toContainText(money(40000));
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: 'Следующий день' }).click();
  await expect(page.getByLabel('Дата доставки')).toHaveValue('2026-12-31');
  // A real query interval must run while dirty and preserve the open draft.
  const before = reads;
  await expect.poll(() => reads, { timeout: 15000 }).toBeGreaterThan(before);
  await expect(total).toContainText(money(40000));
  closed = true;
  await expect(
    page
      .getByRole('status')
      .filter({ hasText: 'Приём заказов на эту дату закрыт.' }),
  ).toHaveText(
    'Приём заказов на эту дату закрыт. Изменить состав уже нельзя.',
    { timeout: 15000 },
  );
  await expect(total).toContainText(money(20000));
  await expect(
    page.getByRole('button', { name: 'Добавить Суп', exact: true }),
  ).toBeDisabled();
  if (testInfo.project.name === 'mobile')
    await page.getByRole('button', { name: /^Мой план/ }).click();
  await expect(
    page.getByRole('heading', { name: 'План на четверг' }),
  ).toBeVisible();
  await expect(page.getByText('Приём закрыт', { exact: true })).toBeVisible();
  await expect(
    page
      .getByRole('status')
      .filter({ hasText: 'Приём заказов на эту дату закрыт.' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Увеличить Суп' }),
  ).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Сохранить план' }),
  ).toHaveCount(0);
  await expect(page.getByText('Есть несохранённые изменения')).toHaveCount(0);
  await expect(page.getByText(/16:00|cutoff|draft|locked/)).toHaveCount(0);
  priced = true;
  await page.reload();
  if (testInfo.project.name === 'mobile')
    await page.getByRole('button', { name: /^Мой план/ }).click();
  await expect(page.getByText(/↑ Цена выросла/)).toBeVisible();
  await expect(page.getByText(/↓ Цена снизилась/)).toBeVisible();
  await expect(
    page.getByText('Нет в меню Mealty', { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator('.plan-total').filter({ hasText: 'К закупке' }),
  ).toContainText(money(40000));
  await expect(page.locator('.price-change')).toHaveCount(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath(`planning-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
