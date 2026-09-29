import { expect, test } from '@playwright/test';

// Explicit live suite: requires the separately seeded qa/login.compose.yml.
// No page.route(), demo buttons, dependency overrides, or mocked responses.
const accounts = [
  { account: 'employee', role: 'employee', label: 'Сотрудник' },
  { account: 'employee2', role: 'employee', label: 'Сотрудник' },
  { account: 'procurement', role: 'procurement', label: 'Закупки' },
  { account: 'admin', role: 'admin', label: 'Администратор' },
] as const;

for (const { account, role, label } of accounts) {
  test(`${account}: wrong password, real login, role, reload, logout`, async ({
    page,
  }, testInfo) => {
    const failedRequests: { path: string; status: number }[] = [];
    const authPaths = new Set(['/api/auth/login', '/api/me']);
    page.on('response', (response) => {
      const path = new URL(response.url()).pathname;
      if (authPaths.has(path) && response.status() >= 400) {
        failedRequests.push({ path, status: response.status() });
      }
    });
    await page.goto('/');
    await page.getByLabel('Рабочая почта').fill(`${account}@kis.local`);
    await page.getByLabel('Пароль', { exact: true }).fill('wrong-qa-password');
    const denied = page.waitForResponse('**/api/auth/login');
    await page.getByRole('button', { name: 'Войти →' }).click();
    expect((await denied).status()).toBe(401);
    await expect(page.getByRole('alert')).toHaveText(
      'Сессия завершена или неверная почта / пароль. Войдите снова.',
    );
    expect(
      await page.evaluate(() => localStorage.getItem('corplunch.access_token')),
    ).toBeNull();
    await page.screenshot({ path: testInfo.outputPath('wrong-password.png') });

    await page.getByLabel('Пароль', { exact: true }).fill(account);
    const login = page.waitForResponse('**/api/auth/login');
    const me = page.waitForResponse('**/api/me');
    await page.getByRole('button', { name: 'Войти →' }).click();
    const loginResponse = await login;
    expect(loginResponse.status()).toBe(200);
    const profileResponse = await me;
    expect(profileResponse.status()).toBe(200);
    const profile = await profileResponse.json();
    expect(profile.email).toBe(`${account}@kis.local`);
    expect(profile.role).toBe(role);
    expect(profile).not.toHaveProperty('password_hash');
    expect(
      profileResponse.request().headers().authorization?.startsWith('Bearer '),
    ).toBe(true);
    expect(profileResponse.request().headers().cookie).toBeUndefined();

    const home = role === 'employee' ? '/catalog' : '/orders';
    await expect(page).toHaveURL(new RegExp(`${home}$`));
    await expect(page.locator('.profile')).toContainText(profile.full_name);
    await expect(page.locator('.profile')).toContainText(label);
    await expect(page.locator('.demo-bar')).toHaveCount(0);
    const nav = page.getByRole('navigation', { name: 'Основная навигация' });
    await expect(nav.getByRole('link')).toHaveText(
      role === 'employee'
        ? ['Меню и план']
        : role === 'admin'
          ? ['Сводка дня', 'Статистика', 'Управление']
          : ['Сводка дня', 'Статистика'],
    );
    await page.locator('header').screenshot({
      path: testInfo.outputPath('signed-in.png'),
    });

    const storageKeys = await page.evaluate(() => Object.keys(localStorage));
    expect(storageKeys).toEqual(['corplunch.access_token']);
    const restored = page.waitForResponse('**/api/me');
    await page.reload();
    expect((await restored).status()).toBe(200);
    await expect(page.locator('.profile')).toContainText(profile.full_name);

    for (const path of role === 'employee'
      ? ['/admin', '/orders', '/stats']
      : ['/admin']) {
      await page.goto(path);
      await expect(page).toHaveURL(
        new RegExp(`${role === 'admin' ? path : home}$`),
      );
    }
    await expect(page.locator('.profile')).toContainText(profile.full_name);
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    await expect(page.getByLabel('Рабочая почта')).toBeVisible();
    expect(
      await page.evaluate(() => localStorage.getItem('corplunch.access_token')),
    ).toBeNull();
    await page.reload();
    await expect(page.getByLabel('Рабочая почта')).toBeVisible();

    await testInfo.attach('observations', {
      body: JSON.stringify({
        account,
        role: profile.role,
        userId: profile.id,
        loginStatus: loginResponse.status(),
        profileStatus: profileResponse.status(),
        failedRequests,
      }),
      contentType: 'application/json',
    });
  });
}

for (const [method, path] of [
  ['GET', '/api/me'],
  ['GET', '/api/catalog'],
  ['POST', '/api/catalog/sync'],
  ['GET', '/api/admin/users'],
  ['GET', '/api/admin/departments'],
] as const) {
  test(`no token: ${method} ${path} returns 401`, async ({ request }) => {
    const response = await request.fetch(path, { method });
    expect(response.status()).toBe(401);
    expect(response.headers()['www-authenticate']).toBe('Bearer');
    expect(await response.json()).toEqual({ detail: 'Not authenticated' });
  });
}

test('real tokens identify two distinct employees and enforce admin rights', async ({
  request,
}) => {
  const employeeIds: number[] = [];
  for (const { account, role } of accounts) {
    const login = await request.post('/api/auth/login', {
      data: { email: `${account}@kis.local`, password: account },
    });
    expect(login.status()).toBe(200);
    const { access_token: token, token_type: tokenType } = await login.json();
    expect(tokenType).toBe('bearer');
    const headers = { Authorization: `Bearer ${token}` };
    const me = await request.get('/api/me', { headers });
    expect(me.status()).toBe(200);
    const profile = await me.json();
    expect(profile.role).toBe(role);
    expect(profile.email).toBe(`${account}@kis.local`);
    if (role === 'employee') employeeIds.push(profile.id);
    const users = await request.get('/api/admin/users', { headers });
    expect(users.status()).toBe(role === 'admin' ? 200 : 403);
    if (role === 'employee') {
      const sync = await request.post('/api/catalog/sync', { headers });
      expect(sync.status()).toBe(403);
    }
  }
  expect(employeeIds).toHaveLength(2);
  expect(new Set(employeeIds).size).toBe(2);
});

test('invalid token is rejected', async ({ request }) => {
  const response = await request.get('/api/me', {
    headers: { Authorization: 'Bearer invalid-qa-token' },
  });
  expect(response.status()).toBe(401);
  expect(await response.json()).toEqual({ detail: 'Invalid token' });
});
