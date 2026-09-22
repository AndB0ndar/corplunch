import { expect, test, type Page } from '@playwright/test';
async function enter(page: Page, role: string) {
  await page.getByRole('button', { name: role, exact: true }).click();
}
async function planTab(page: Page, isMobile: boolean) {
  // isVisible() returns immediately and can miss the tab while login renders.
  if (isMobile) {
    const button = page.getByRole('button', { name: /^Мой план/ });
    await button.click();
    await expect(button).toHaveAttribute('aria-pressed', 'true');
  }
  await expect(page.locator('.plan-panel')).toBeVisible();
}
test('two employees → cutoff → export → statistics → locked employee plan', async ({
  page,
  isMobile,
}) => {
  await page.goto('/');
  await enter(page, 'Сотрудник');
  await page
    .getByRole('button', { name: 'Добавить Картофельные ньокки', exact: true })
    .click();
  await page
    .getByRole('button', {
      name: 'Добавить Салат с печёной свёклой',
      exact: true,
    })
    .click();
  await planTab(page, isMobile);
  await page.getByRole('button', { name: 'Сохранить план' }).click();
  await expect(page.getByText('✓ План сохранён')).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click();
  await enter(page, 'Сотрудник 2');
  await page
    .getByRole('button', { name: 'Добавить Картофельные ньокки', exact: true })
    .click();
  await planTab(page, isMobile);
  await page.getByRole('button', { name: 'Сохранить план' }).click();
  await expect(page.getByText('✓ План сохранён')).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click();
  await enter(page, 'Закупки');
  await page.getByRole('button', { name: 'Закрыть приём заказов' }).click();
  await page.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(
    page.getByText('Приём закрыт. Цены и наличие уточнены.'),
  ).toBeVisible();
  await expect(
    page.getByRole('cell', { name: 'Салат с печёной свёклой', exact: true }),
  ).toHaveCount(0);
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать CSV' }).click();
  expect((await downloadEvent).suggestedFilename()).toMatch(/\.csv$/);
  await page
    .getByRole('button', { name: 'Заказ размещён', exact: true })
    .click();
  await page.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(
    page.getByRole('button', { name: '✓ Заказ размещён' }),
  ).toBeDisabled();
  await page.getByRole('link', { name: 'Статистика' }).click();
  await expect(
    page.getByRole('heading', { name: 'Любимые блюда' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click();
  await enter(page, 'Сотрудник');
  await planTab(page, isMobile);
  await expect(
    page.getByText('Нет в меню Mealty', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Сохранить план' }),
  ).toHaveCount(0);
});
test('admin edits departments, people and settings', async ({ page }) => {
  await page.goto('/');
  await enter(page, 'Администратор');
  await page.getByRole('link', { name: 'Управление' }).click();
  await expect(
    page.getByRole('heading', { name: 'Команда', exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel('Новый отдел', { exact: true }).fill('Дизайн');
  await page.getByRole('button', { name: 'Добавить отдел' }).click();
  await expect(page.getByText('Отдел сохранён.')).toBeVisible();
  await page.getByRole('button', { name: '+ Сотрудник', exact: true }).click();
  await page.getByLabel('Имя и фамилия').fill('Тестовый Сотрудник');
  await page.getByLabel('Почта', { exact: true }).fill('qa@example.com');
  await page.getByLabel('Временный пароль').fill('demo-test');
  await page
    .getByRole('combobox', { name: 'Отдел', exact: true })
    .selectOption({ label: 'Дизайн' });
  await page.getByRole('button', { name: 'Сохранить сотрудника' }).click();
  await expect(
    page.getByRole('cell', { name: /^Тестовый Сотрудник/ }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Изменить Тестовый Сотрудник' })
    .click();
  await page.getByLabel('Учётная запись активна').uncheck();
  await page.getByRole('button', { name: 'Сохранить сотрудника' }).click();
  await expect(page.getByText('Отключён', { exact: true })).toBeVisible();
  await page.getByLabel('Общий лимит ₽ / день').fill('700,50');
  await page.getByRole('button', { name: 'Сохранить настройки' }).click();
  await expect(page.getByText('✓ Настройки сохранены')).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
test('live login uses API; role routes are guarded; network errors stay visible', async ({
  page,
}) => {
  await page.route('**/api/auth/login', (route) =>
    route.fulfill({ json: { access_token: 'qa-token', token_type: 'bearer' } }),
  );
  await page.route('**/api/me', (route) => {
    expect(route.request().headers().authorization).toBe('Bearer qa-token');
    return route.fulfill({
      json: {
        id: 1,
        email: 'qa@example.com',
        full_name: 'QA',
        role: 'employee',
        department: null,
        daily_limit_kopecks: null,
      },
    });
  });
  await page.route('**/api/catalog?*', (route) =>
    route.fulfill({ status: 502, json: { detail: 'Mealty недоступен' } }),
  );
  await page.route('**/api/plans/*', (route) =>
    route.fulfill({
      json: {
        id: null,
        user_id: 1,
        delivery_date: '2026-09-20',
        status: 'draft',
        editable: true,
        planned_total_kopecks: 0,
        actual_total_kopecks: null,
        items: [],
      },
    }),
  );
  await page.goto('/');
  await page.getByLabel('Рабочая почта').fill('qa@example.com');
  await page.getByLabel('Пароль', { exact: true }).fill('test');
  await page.getByRole('button', { name: 'Войти →' }).click();
  await expect(page.getByRole('alert')).toHaveText('Mealty недоступен');
  await page.goto('/admin');
  await expect(page).toHaveURL(/\/catalog$/);
  await expect(page.getByRole('link', { name: 'Управление' })).toHaveCount(0);
});
