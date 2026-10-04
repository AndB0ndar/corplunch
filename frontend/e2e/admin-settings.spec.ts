import { expect, test } from '@playwright/test';

test('admin settings sends full PUT, retains failed edits and persists successful values', async ({
  page,
}, testInfo) => {
  const admin = {
    id: 4,
    email: 'admin@qa.local',
    full_name: 'Администратор QA',
    role: 'admin',
    department: null,
    daily_limit_kopecks: null,
    is_active: true,
  };
  let settings = {
    cutoff_time: '16:00',
    timezone: 'Europe/Moscow',
    mealty_city: 'Москва',
    daily_limit_kopecks: null as number | null,
    catalog_sync_per_day: 2,
  };
  let rejectSave = true;
  const savedBodies: unknown[] = [];
  await page.route('**/api/auth/login', (route) =>
    route.fulfill({
      json: { access_token: 'admin-contract-token', token_type: 'bearer' },
    }),
  );
  await page.route('**/api/me', (route) => route.fulfill({ json: admin }));
  await page.route('**/api/admin/users', (route) =>
    route.fulfill({ json: [admin] }),
  );
  await page.route('**/api/admin/departments', (route) =>
    route.fulfill({ json: [{ id: 1, name: 'Разработка' }] }),
  );
  await page.route('**/api/admin/settings', async (route) => {
    expect(route.request().headers().authorization).toBe(
      'Bearer admin-contract-token',
    );
    if (route.request().method() === 'GET')
      return route.fulfill({ json: settings });
    expect(route.request().method()).toBe('PUT');
    const body = route.request().postDataJSON();
    savedBodies.push(body);
    if (rejectSave) {
      rejectSave = false;
      return route.fulfill({
        status: 422,
        json: { detail: 'Проверьте время закрытия приёма.' },
      });
    }
    settings = body;
    await route.fulfill({ json: settings });
  });
  await page.goto('/admin');
  await page.getByLabel('Рабочая почта').fill(admin.email);
  await page.getByLabel('Пароль', { exact: true }).fill('contract-test');
  await page.getByRole('button', { name: 'Войти →' }).click();
  await expect(
    page.getByRole('heading', { name: 'Команда', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Изменить Администратор QA' }).click();
  await expect(page.getByLabel('Новый пароль (необязательно)')).toHaveCount(0);
  await page.getByRole('button', { name: 'Отмена', exact: true }).click();
  await page.getByLabel('Закрытие приёма').fill('15:30');
  await page.getByLabel('Город Mealty').fill('Санкт-Петербург');
  await page.getByLabel('Общий лимит ₽ / день').fill('700,50');
  await page.getByRole('button', { name: 'Сохранить настройки' }).click();
  await expect(page.getByRole('alert')).toHaveText(
    'Проверьте время закрытия приёма.',
  );
  await expect(page.getByLabel('Общий лимит ₽ / день')).toHaveValue('700,50');
  await expect(page.getByText('✓ Настройки сохранены')).toHaveCount(0);
  await page.getByRole('button', { name: 'Сохранить настройки' }).click();
  await expect(page.getByText('✓ Настройки сохранены')).toBeVisible();
  const expected = {
    cutoff_time: '15:30',
    timezone: 'Europe/Moscow',
    mealty_city: 'Санкт-Петербург',
    daily_limit_kopecks: 70050,
    catalog_sync_per_day: 2,
  };
  expect(savedBodies).toEqual([expected, expected]);
  await page.reload();
  await expect(page.getByLabel('Закрытие приёма')).toHaveValue('15:30');
  await expect(page.getByLabel('Город Mealty')).toHaveValue('Санкт-Петербург');
  await expect(page.getByLabel('Общий лимит ₽ / день')).toHaveValue('700.5');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath('admin-settings.png'),
    fullPage: true,
  });
});
