import { beforeEach, describe, expect, it } from 'vitest';
import { demoApi as api, resetDemo } from './demo';
import { shiftDate, today } from './format';
const date = shiftDate(today(), 2);
const login = (name: string) => api.login(`${name}@kis.local`, name);
beforeEach(resetDemo);
describe('Offline regression scenario', () => {
  it('aggregates two employees, freezes prices, excludes unavailable dishes and makes cutoff/place idempotent', async () => {
    await login('employee');
    await api.savePlan(date, [
      { dish_id: 1, qty: 2 },
      { dish_id: 4, qty: 1 },
    ]);
    await login('employee2');
    await api.savePlan(date, [{ dish_id: 1, qty: 1 }]);
    await login('procurement');
    await api.cutoff(date);
    const order = await api.order(date);
    expect(order.items).toHaveLength(1);
    expect(order.items[0].qty).toBe(3);
    expect(order.totals.actual_kopecks).toBe(127500);
    expect(order.by_employee).toHaveLength(2);
    expect(order.totals.unavailable_count).toBe(1);
    await api.cutoff(date);
    expect(await api.order(date)).toEqual(order);
    await api.place(date);
    await api.place(date);
    expect((await api.order(date)).status).toBe('placed');
    const stats = await api.stats({ from: date, to: date });
    expect(stats.total_actual_kopecks).toBe(127500);
    await login('employee');
    expect((await api.plan(date)).editable).toBe(false);
    await expect(api.savePlan(date, [])).rejects.toMatchObject({ status: 403 });
  });
  it('rejects foreign employee plans and procurement admin access', async () => {
    await login('employee');
    await expect(api.plan(date, 2)).rejects.toMatchObject({ status: 403 });
    await expect(api.order(date)).rejects.toMatchObject({ status: 403 });
    await login('procurement');
    await expect(api.users()).rejects.toMatchObject({ status: 403 });
    await expect(api.place(date)).rejects.toMatchObject({ status: 403 });
  });
  it('honors system limits and refresh quota', async () => {
    await login('admin');
    const settings = await api.settings();
    await api.saveSettings({
      ...settings,
      daily_limit_kopecks: 10000,
      catalog_sync_per_day: 1,
    });
    await api.sync();
    await expect(api.sync()).rejects.toMatchObject({ status: 429 });
    await login('employee');
    await expect(
      api.savePlan(date, [{ dish_id: 1, qty: 1 }]),
    ).rejects.toMatchObject({ status: 422 });
    expect((await api.plan(date)).items).toEqual([]);
  });
});
