import { expect, test } from '@playwright/test';

test('live settings persist full PUT and quota boundaries after reload', async ({
  page,
}, testInfo) => {
  await page.goto('/admin');
  await page.getByLabel('Рабочая почта').fill('admin@kis.local');
  await page.getByLabel('Пароль', { exact: true }).fill('admin');
  const initialSettings = page.waitForResponse(
    (r) =>
      r.url().endsWith('/api/admin/settings') && r.request().method() === 'GET',
  );
  await page.getByRole('button', { name: 'Войти →' }).click();
  const originalResponse = await initialSettings;
  expect(originalResponse.status()).toBe(200);
  const original = await originalResponse.json();
  async function save() {
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/admin/settings') &&
        r.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Сохранить настройки' }).click();
    const saved = await response;
    expect(saved.status()).toBe(200);
    await expect(page.getByText('✓ Настройки сохранены')).toBeVisible();
    return saved;
  }
  try {
    await page.getByLabel('Закрытие приёма').fill('15:30');
    await page.getByLabel('Город Mealty').fill('Санкт-Петербург');
    await page.getByLabel('Общий лимит ₽ / день').fill('700,50');
    await page.getByLabel('Обновлений каталога в сутки').fill('0');
    const saved = await save();
    const expected = {
      ...original,
      cutoff_time: '15:30',
      mealty_city: 'Санкт-Петербург',
      daily_limit_kopecks: 70050,
      catalog_sync_per_day: 0,
    };
    expect(saved.request().postDataJSON()).toEqual(expected);
    expect(await saved.json()).toEqual(expected);
    await page.reload();
    await expect(page.getByLabel('Закрытие приёма')).toHaveValue('15:30');
    await expect(page.getByLabel('Город Mealty')).toHaveValue(
      'Санкт-Петербург',
    );
    await expect(page.getByLabel('Общий лимит ₽ / день')).toHaveValue('700.5');
    await expect(page.getByLabel('Обновлений каталога в сутки')).toHaveValue(
      '0',
    );
    await page.screenshot({
      path: testInfo.outputPath('settings-live.png'),
      fullPage: true,
    });
    await page.getByLabel('Общий лимит ₽ / день').fill('');
    await page.getByLabel('Обновлений каталога в сутки').fill('100');
    const upper = await save();
    expect(await upper.json()).toMatchObject({
      daily_limit_kopecks: null,
      catalog_sync_per_day: 100,
    });
    await page.reload();
    await expect(page.getByLabel('Общий лимит ₽ / день')).toHaveValue('');
    await expect(page.getByLabel('Обновлений каталога в сутки')).toHaveValue(
      '100',
    );
    await page.getByLabel('Обновлений каталога в сутки').fill('101');
    expect(
      await page
        .getByLabel('Обновлений каталога в сутки')
        .evaluate((el: HTMLInputElement) => el.validity.rangeOverflow),
    ).toBe(true);
    await testInfo.attach('settings-observations', {
      body: JSON.stringify({
        fullPut: true,
        persistedAfterReload: true,
        quotaZero: true,
        quotaHundred: true,
        emptyLimit: null,
        quotaAboveHundredRejected: true,
      }),
      contentType: 'application/json',
    });
  } finally {
    await page.getByLabel('Закрытие приёма').fill(original.cutoff_time);
    await page.getByLabel('Город Mealty').fill(original.mealty_city);
    await page
      .getByLabel('Общий лимит ₽ / день')
      .fill(
        original.daily_limit_kopecks === null
          ? ''
          : String(original.daily_limit_kopecks / 100),
      );
    await page
      .getByLabel('Обновлений каталога в сутки')
      .fill(String(original.catalog_sync_per_day));
    const restored = await save();
    expect(await restored.json()).toEqual(original);
  }
});

test('live admin returns active status and preserves disabled users during edits', async ({
  page,
  request,
}, testInfo) => {
  const suffix = Date.now().toString();
  const department = `QA ${suffix}`;
  const renamedDepartment = `${department} новый`;
  const email = `qa-${suffix}@kis.local`;
  const fullName = `QA сотрудник ${suffix}`;
  const updatedName = `${fullName} изменён`;
  const password = 'qa-temporary-password';
  await page.goto('/admin');
  await page.getByLabel('Рабочая почта').fill('admin@kis.local');
  await page.getByLabel('Пароль', { exact: true }).fill('admin');
  await page.getByRole('button', { name: 'Войти →' }).click();
  await page.getByLabel('Новый отдел', { exact: true }).fill(department);
  const createdDepartment = page.waitForResponse(
    (r) =>
      r.url().endsWith('/api/admin/departments') &&
      r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Добавить отдел' }).click();
  expect((await createdDepartment).status()).toBe(201);
  await page
    .getByRole('button', {
      name: `${department} — изменить отдел`,
      exact: true,
    })
    .click();
  await page.getByLabel('Название отдела').fill(renamedDepartment);
  await page.getByRole('button', { name: 'Сохранить отдел' }).click();
  await expect(
    page.getByRole('button', {
      name: `${renamedDepartment} — изменить отдел`,
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole('button', { name: '+ Сотрудник', exact: true }).click();
  await page.getByLabel('Имя и фамилия').fill(fullName);
  await page.getByLabel('Почта', { exact: true }).fill(email);
  await page.getByLabel('Временный пароль').fill(password);
  await page
    .getByRole('combobox', { name: 'Отдел', exact: true })
    .selectOption({ label: renamedDepartment });
  await page.getByLabel('Лимит ₽ / день', { exact: true }).fill('700,50');
  await page.getByLabel('Учётная запись активна').uncheck();
  const createdUser = page.waitForResponse(
    (r) =>
      r.url().endsWith('/api/admin/users') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Сохранить сотрудника' }).click();
  const response = await createdUser;
  expect(response.status()).toBe(201);
  const created = await response.json();
  expect(created.daily_limit_kopecks).toBe(70050);
  expect(created.department.name).toBe(renamedDepartment);
  const hasStatus = typeof created.is_active === 'boolean';
  expect(created.is_active).toBe(false);
  const userRow = page.getByRole('row').filter({ hasText: email });
  await expect(userRow.getByText('Отключён', { exact: true })).toBeVisible();
  let login = await request.post('/api/auth/login', {
    data: { email, password },
  });
  expect(login.status()).toBe(401);
  await page
    .getByRole('button', { name: `Изменить ${fullName}`, exact: true })
    .click();
  await page.getByLabel('Имя и фамилия').fill(updatedName);
  const updatedUser = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/admin/users/${created.id}`) &&
      r.request().method() === 'PATCH',
  );
  await page.getByRole('button', { name: 'Сохранить сотрудника' }).click();
  const updated = await updatedUser;
  expect(updated.status()).toBe(200);
  expect((await updated.json()).is_active).toBe(false);
  login = await request.post('/api/auth/login', { data: { email, password } });
  expect(login.status()).toBe(401);
  await page
    .getByRole('button', { name: `Изменить ${updatedName}`, exact: true })
    .click();
  await page.getByLabel('Учётная запись активна').check();
  await page
    .getByRole('combobox', { name: 'Роль', exact: true })
    .selectOption('procurement');
  await page
    .getByRole('combobox', { name: 'Отдел', exact: true })
    .selectOption('');
  await page.getByLabel('Лимит ₽ / день', { exact: true }).fill('0');
  const activated = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/admin/users/${created.id}`) &&
      r.request().method() === 'PATCH',
  );
  await page.getByRole('button', { name: 'Сохранить сотрудника' }).click();
  const activatedResponse = await activated;
  expect(activatedResponse.status()).toBe(200);
  expect((await activatedResponse.json()).is_active).toBe(true);
  login = await request.post('/api/auth/login', { data: { email, password } });
  expect(login.status()).toBe(200);
  const token = (await login.json()).access_token;
  const profile = await request.get('/api/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(await profile.json()).toMatchObject({
    role: 'procurement',
    department: null,
    daily_limit_kopecks: 0,
    is_active: true,
  });
  await page.reload();
  await expect(
    page.getByRole('button', {
      name: `Изменить ${updatedName}`,
      exact: true,
    }),
  ).toBeVisible();
  await expect(userRow.getByText('Активен', { exact: true })).toBeVisible();
  await page
    .getByRole('region', { name: 'Команда', exact: true })
    .screenshot({ path: testInfo.outputPath('team.png') });
  await testInfo.attach('observations', {
    body: JSON.stringify({
      createdStatus: response.status(),
      statusFieldReturned: hasStatus,
      disabledLogin: 401,
      nameEditKeptDisabled: true,
      enabledLogin: login.status(),
      role: 'procurement',
      limitKopecks: 0,
    }),
    contentType: 'application/json',
  });
});
