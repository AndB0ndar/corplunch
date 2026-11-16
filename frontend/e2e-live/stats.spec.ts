import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { money } from '../src/format';
import type { Stats } from '../src/types';

// Real HTTP + PostgreSQL. Seed only through tests/.env.test, no route mocks.
// Historical plan prices/unavailable flags are inserted by tests/seed_stats.py.
test('period statistics: sums, departments, exclusions, roles and responsive tables', async ({
  page,
  request,
}, testInfo) => {
  const seed: {
    from: string;
    to: string;
    second_day: string;
    empty_day: string;
    departments: { id: number; name: string }[];
    users: { id: number; name: string }[];
    dishes: number[];
  } = JSON.parse(await readFile('../tests/results/stats-seed.json', 'utf8'));
  const headers = async (account: string) => {
    const response = await request.post('/api/auth/login', {
      data: { email: `${account}@kis.local`, password: account },
    });
    expect(response.status()).toBe(200);
    return { Authorization: `Bearer ${(await response.json()).access_token}` };
  };
  const path = `/api/stats/summary?from=${seed.from}&to=${seed.to}`;
  const procurement = await headers('procurement');
  const admin = await headers('admin');
  const access: Record<string, number> = {};
  access.anonymous = (await request.get(path)).status();
  expect(access.anonymous).toBe(401);
  for (const account of ['employee', 'employee2']) {
    access[account] = (
      await request.get(path, { headers: await headers(account) })
    ).status();
    expect(access[account]).toBe(403);
  }
  const response = await request.get(path, { headers: procurement });
  access.procurement = response.status();
  expect(access.procurement).toBe(200);
  const stats: Stats = await response.json();
  expect(stats).toMatchObject({
    from: seed.from,
    to: seed.to,
    total_planned_kopecks: 213000,
    total_actual_kopecks: 208500,
    delta_kopecks: -4500,
    unavailable_count: 2,
  });
  expect(stats.by_employee).toEqual([
    {
      user_id: seed.users[0].id,
      full_name: seed.users[0].name,
      actual_kopecks: 127500,
      order_count: 2,
    },
    {
      user_id: seed.users[1].id,
      full_name: seed.users[1].name,
      actual_kopecks: 81000,
      order_count: 2,
    },
    {
      user_id: seed.users[2].id,
      full_name: seed.users[2].name,
      actual_kopecks: 0,
      order_count: 1,
    },
  ]);
  expect(stats.by_department).toEqual(
    seed.departments.map((d, i) => ({
      department_id: d.id,
      name: d.name,
      actual_kopecks: [127500, 81000][i],
      order_count: 2,
    })),
  );
  expect(stats.top_dishes).toEqual([
    {
      dish_id: seed.dishes[0],
      name: 'QA Обед подорожал',
      qty: 3,
      actual_kopecks: 127500,
    },
    {
      dish_id: seed.dishes[1],
      name: 'QA Обед подешевел',
      qty: 3,
      actual_kopecks: 81000,
    },
  ]);
  expect(stats.price_changes).toHaveLength(2);
  expect(stats.price_changes).toEqual(
    expect.arrayContaining([
      {
        dish_id: seed.dishes[0],
        name: 'QA Обед подорожал',
        planned_price_kopecks: 41000,
        actual_price_kopecks: 42500,
      },
      {
        dish_id: seed.dishes[1],
        name: 'QA Обед подешевел',
        planned_price_kopecks: 30000,
        actual_price_kopecks: 27000,
      },
    ]),
  );
  const adminResponse = await request.get(path, { headers: admin });
  access.admin = adminResponse.status();
  expect(access.admin).toBe(200);
  expect(await adminResponse.json()).toEqual(stats);
  expect(
    await (await request.get(path, { headers: procurement })).json(),
  ).toEqual(stats);

  const departmentResponse = await request.get(
    `${path}&department_id=${seed.departments[0].id}`,
    { headers: procurement },
  );
  expect(departmentResponse.status()).toBe(200);
  const departmentStats: Stats = await departmentResponse.json();
  expect(departmentStats).toMatchObject({
    total_planned_kopecks: 123000,
    total_actual_kopecks: 127500,
    delta_kopecks: 4500,
    unavailable_count: 1,
  });
  expect(departmentStats.by_employee).toEqual([stats.by_employee[0]]);
  expect(departmentStats.by_department).toEqual([stats.by_department[0]]);
  expect(departmentStats.top_dishes).toEqual([stats.top_dishes[0]]);
  expect(departmentStats.price_changes).toHaveLength(1);

  const second = await request.get(
    `/api/stats/summary?from=${seed.second_day}&to=${seed.to}`,
    { headers: procurement },
  );
  expect(second.status()).toBe(200);
  const secondStats: Stats = await second.json();
  expect(secondStats).toMatchObject({
    total_planned_kopecks: 101000,
    total_actual_kopecks: 96500,
    delta_kopecks: -4500,
    unavailable_count: 0,
  });
  const first = await request.get(
    `/api/stats/summary?from=${seed.from}&to=${seed.from}`,
    { headers: procurement },
  );
  expect(first.status()).toBe(200);
  expect(await first.json()).toMatchObject({
    total_planned_kopecks: 112000,
    total_actual_kopecks: 112000,
    delta_kopecks: 0,
    unavailable_count: 2,
  });
  for (const emptyPath of [
    `${path}&department_id=2147483647`,
    `/api/stats/summary?from=${seed.empty_day}&to=${seed.empty_day}`,
  ]) {
    const empty = await request.get(emptyPath, { headers: procurement });
    expect(empty.status()).toBe(200);
    expect(await empty.json()).toMatchObject({
      total_planned_kopecks: 0,
      total_actual_kopecks: 0,
      delta_kopecks: 0,
      unavailable_count: 0,
      by_employee: [],
      by_department: [],
      top_dishes: [],
      price_changes: [],
    });
  }
  const invalid = await request.get(
    `/api/stats/summary?from=${seed.to}&to=${seed.from}`,
    { headers: procurement },
  );
  expect(invalid.status()).toBe(422);
  expect(await invalid.json()).toHaveProperty('detail');

  await page.goto('/stats');
  await page.getByLabel('Рабочая почта').fill('procurement@kis.local');
  await page.getByLabel('Пароль', { exact: true }).fill('procurement');
  await page.getByRole('button', { name: 'Войти →' }).click();
  await expect(
    page.getByRole('heading', { name: 'Статистика.' }),
  ).toBeVisible();
  await page.getByLabel('По', { exact: true }).fill(seed.to);
  await page.getByLabel('С', { exact: true }).fill(seed.from);
  const departments = page.getByRole('table', { name: 'Расходы по отделам' });
  await expect(departments.getByRole('row')).toHaveCount(3);
  await expect(departments).toContainText(money(127500));
  await expect(departments).toContainText(money(81000));
  await expect(page.locator('.metrics')).toContainText(money(213000));
  await expect(page.locator('.metrics')).toContainText(money(208500));
  await expect(page.getByText('QA Снятое блюдо', { exact: true })).toHaveCount(
    0,
  );
  await expect(page.locator('.bar-track')).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath('statistics.png'),
    fullPage: true,
  });

  await page
    .getByRole('combobox', { name: 'Отдел', exact: true })
    .selectOption(String(seed.departments[0].id));
  await expect(departments.getByRole('row')).toHaveCount(2);
  await expect(
    page.getByRole('cell', { name: seed.users[1].name, exact: true }),
  ).toHaveCount(0);
  await expect(page.locator('.metrics')).toContainText(money(123000));
  await page.getByLabel('С', { exact: true }).fill(seed.second_day);
  await expect(
    page.getByRole('combobox', { name: 'Отдел', exact: true }),
  ).toHaveValue('');
  await expect(page.locator('.metrics')).toContainText(money(96500));
  await page.getByLabel('По', { exact: true }).fill(seed.empty_day);
  await page.getByLabel('С', { exact: true }).fill(seed.empty_day);
  await expect(
    page.getByText(/В этом периоде пока нет закрытых заказов/),
  ).toBeVisible();
  await page.getByLabel('По', { exact: true }).fill(seed.from);
  await expect(page.getByRole('alert')).toContainText(
    'Дата начала должна быть не позже даты окончания.',
  );
  await testInfo.attach('observations', {
    body: JSON.stringify(
      {
        seed,
        access,
        stats,
        departmentStats,
        secondStats,
        inverted_range_status: invalid.status(),
      },
      null,
      2,
    ),
    contentType: 'application/json',
  });
});
