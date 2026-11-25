import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { shiftDate, today, money } from '../src/format';
import type { Order } from '../src/types';

test('защита: два плана → cutoff → CSV → размещение → статистика → админка', async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(120_000);
  const marker = await request.get('/api/qa/defense');
  expect(await marker.json(), 'Запустите tests/start-defense.ps1').toEqual({
    provider: 'local-html',
  });
  const external: string[] = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== new URL(baseURL!).origin) {
      external.push(url.origin);
      await route.abort();
    } else await route.continue();
  });
  async function login(account: string, path: string) {
    await page.goto(path);
    await page.getByLabel('Рабочая почта').fill(account + '@kis.local');
    await page.getByLabel('Пароль', { exact: true }).fill(account);
    await page.getByRole('button', { name: 'Войти →' }).click();
    await expect(page.getByRole('button', { name: 'Выйти' })).toBeVisible();
  }
  const button = (name: string) =>
    page.getByRole('button', { name, exact: true });
  async function token(account: string) {
    const response = await request.post('/api/auth/login', {
      data: { email: account + '@kis.local', password: account },
    });
    expect(response.ok()).toBe(true);
    return { Authorization: 'Bearer ' + (await response.json()).access_token };
  }
  const headers = await token('admin');
  let date = shiftDate(today(), 2);
  for (let i = 0; ; i++) {
    const response = await request.get('/api/orders/' + date, { headers });
    expect(response.ok()).toBe(true);
    const order: Order = await response.json();
    if (order.status === 'collecting' && !order.by_employee.length) break;
    if (i >= 89) throw new Error('Нет свободной даты');
    date = shiftDate(date, 1);
  }
  const soup = 'Солянка мясная',
    removed = 'Котлетки из морепродуктов';
  for (const account of ['employee', 'employee2']) {
    await login(account, '/catalog');
    await page.getByLabel('Дата доставки').fill(date);
    await button('Добавить ' + soup).click();
    if (account === 'employee') await button('Добавить ' + removed).click();
    const saved = page.waitForResponse(
      (r) =>
        r.url().endsWith('/plans/' + date) && r.request().method() === 'PUT',
    );
    await button('Сохранить план').click();
    expect((await (await saved).json()).planned_total_kopecks).toBe(
      account === 'employee' ? 68000 : 27000,
    );
    await expect(page.getByText('✓ План сохранён')).toBeVisible();
    await button('Выйти').click();
  }
  await login('procurement', '/orders');
  await page.getByLabel('Дата доставки').fill(date);
  await expect(page.locator('.employee-row')).toHaveCount(2);
  const closed = page.waitForResponse((r) =>
    r.url().endsWith('/' + date + '/cutoff'),
  );
  await button('Закрыть приём заказов').click();
  await button('Подтвердить').click();
  expect(await (await closed).json()).toMatchObject({
    sync: 'ok',
    plans_closed: 2,
    items_unavailable: 1,
  });
  const table = page.getByRole('table').first();
  await expect(table).toContainText(money(57000));
  await expect(table).not.toContainText(removed);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать список для заказа' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('corplunch-' + date + '.csv');
  const csv = (await readFile((await file.path())!, 'utf8'))
    .trim()
    .split(/\r?\n/);
  expect(csv).toEqual([
    'external_id,name,qty,unit_price_kopecks,line_total_kopecks',
    '721,Солянка мясная,2,28500,57000',
  ]);
  await button('Заказ размещён').click();
  await button('Подтвердить').click();
  await expect(button('✓ Заказ размещён')).toBeDisabled();
  await button('Выйти').click();
  await login('employee', '/catalog');
  await page.getByLabel('Дата доставки').fill(date);
  await expect(page.getByText('Приём закрыт', { exact: true })).toBeVisible();
  await expect(page.locator('.plan-list')).toContainText('Нет в меню Mealty');
  await expect(page.locator('.plan-list .price-change')).toContainText(
    money(28500),
  );
  await expect(button('Добавить ' + soup)).toBeDisabled();
  await button('Выйти').click();
  await login('procurement', '/stats');
  await page.getByLabel('По', { exact: true }).fill(date);
  await page.getByLabel('С', { exact: true }).fill(date);
  const department = page.getByRole('combobox', { name: 'Отдел' });
  await department.selectOption({ label: 'Разработка' });
  await expect(page.locator('.metrics')).toContainText(money(54000));
  await expect(page.locator('.metrics')).toContainText(money(57000));
  await expect(page.locator('.metrics')).toContainText('+' + money(3000));
  await expect(
    page.getByRole('table', { name: 'Расходы по отделам' }),
  ).toContainText(money(57000));
  await expect(page.locator('.ranking')).toHaveCount(1);
  await expect(page.locator('.ranking')).toContainText(soup);
  for (const person of ['Иван Сотрудник', 'Пётр Сотрудник'])
    await expect(page.getByRole('cell', { name: person })).toBeVisible();
  const chart = page.getByRole('region', { name: 'Расходы по дням' });
  await expect(chart.getByRole('listitem')).toHaveText([new RegExp('570')]);
  await page.getByLabel('По', { exact: true }).fill(shiftDate(date, 7));
  await expect(chart.getByRole('listitem')).toHaveCount(7);
  await expect(chart.getByRole('listitem').first()).toContainText(money(57000));
  await button('Следующие дни').click();
  await expect(chart.locator('time')).toHaveAttribute(
    'datetime',
    shiftDate(date, 7),
  );
  await button('Предыдущие дни').click();
  await expect(chart.getByRole('listitem')).toHaveCount(7);
  await button('Выйти').click();
  await login('admin', '/admin');
  await button('+ Сотрудник').click();
  const email = 'defense-' + Date.now() + '@qa.local';
  await page.getByLabel('Имя и фамилия').fill('Сотрудник для защиты');
  await page.getByLabel('Почта', { exact: true }).fill(email);
  await page.getByLabel('Временный пароль').fill('test-defense-only');
  await page.getByLabel('Учётная запись активна').uncheck();
  await button('Сохранить сотрудника').click();
  await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible();
  const cutoff = page.getByLabel('Закрытие приёма');
  const original = await cutoff.inputValue();
  const changed = original === '15:45' ? '15:30' : '15:45';
  async function saveCutoff(value: string) {
    await cutoff.fill(value);
    const put = page.waitForResponse(
      (r) =>
        r.url().endsWith('/admin/settings') && r.request().method() === 'PUT',
    );
    await button('Сохранить настройки').click();
    expect((await (await put).json()).cutoff_time).toBe(value);
  }
  try {
    await saveCutoff(changed);
    await page.reload();
    await expect(cutoff).toHaveValue(changed);
    await expect(
      page.getByRole('row').filter({ hasText: email }),
    ).toBeVisible();
  } finally {
    await saveCutoff(original);
  }
  expect(external).toEqual([]);
});
