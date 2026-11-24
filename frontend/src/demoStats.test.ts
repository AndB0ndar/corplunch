import { expect, it } from 'vitest';
import { demoStats } from './demoStats';
import type { Plan, PlanItem, User } from './types';

const users: User[] = [1, 2, 3].map((id) => ({
  id,
  email: `${id}@test.local`,
  full_name: `Сотрудник ${id}`,
  role: 'employee',
  department: id === 3 ? null : { id, name: `Отдел ${id}` },
  daily_limit_kopecks: null,
  is_active: true,
}));
const item: PlanItem = {
  dish_id: 1,
  name: 'Обед',
  qty: 2,
  planned_price_kopecks: 41000,
  actual_price_kopecks: 42500,
  unavailable: false,
};
function plan(overrides: Partial<Plan> = {}): Plan {
  return {
    id: 1,
    user_id: 1,
    delivery_date: '2026-11-16',
    status: 'included_in_order',
    editable: false,
    planned_total_kopecks: 118000,
    actual_total_kopecks: 85000,
    items: [
      item,
      {
        ...item,
        dish_id: 2,
        name: 'Снятое блюдо',
        qty: 3,
        planned_price_kopecks: 36000,
        actual_price_kopecks: null,
        unavailable: true,
      },
    ],
    ...overrides,
  };
}
const period = { from: '2026-11-16', to: '2026-11-17' };

it('uses only available lines for both sums and deduplicates price triples across people and dates', () => {
  const stats = demoStats(
    [plan(), plan({ user_id: 2 }), plan({ delivery_date: period.to })],
    users,
    period,
  );
  expect(stats).toMatchObject({
    total_planned_kopecks: 246000,
    total_actual_kopecks: 255000,
    delta_kopecks: 9000,
    unavailable_count: 3,
  });
  expect(stats.price_changes).toHaveLength(1);
  expect(stats.top_dishes).toEqual([
    { dish_id: 1, name: 'Обед', qty: 6, actual_kopecks: 255000 },
  ]);
  expect(stats.by_employee[0]).toMatchObject({
    order_count: 2,
    actual_kopecks: 170000,
  });
});

it('includes range boundaries and only included_in_order; department slices every total', () => {
  const excluded: Plan[] = ['draft', 'locked', 'priced'].map((status) =>
    plan({ status: status as Plan['status'] }),
  );
  const plans = [
    plan(),
    plan({ user_id: 2, delivery_date: period.to }),
    ...excluded,
    plan({ delivery_date: '2026-11-15' }),
    plan({ delivery_date: '2026-11-18' }),
  ];
  expect(demoStats(plans, users, period).by_employee).toHaveLength(2);
  const stats = demoStats(plans, users, { ...period, department_id: 2 });
  expect(stats).toMatchObject({
    total_planned_kopecks: 82000,
    total_actual_kopecks: 85000,
    unavailable_count: 1,
  });
  expect(stats.by_employee).toHaveLength(1);
  expect(stats.by_department.map((d) => d.department_id)).toEqual([2]);
  expect(
    demoStats(plans, users, { ...period, department_id: 999 }).by_employee,
  ).toEqual([]);
});

it('counts an all-unavailable plan and an employee without a department', () => {
  const stats = demoStats(
    [plan({ user_id: 3, items: [plan().items[1]] })],
    users,
    period,
  );
  expect(stats).toMatchObject({
    total_planned_kopecks: 0,
    total_actual_kopecks: 0,
    delta_kopecks: 0,
    unavailable_count: 1,
    by_department: [],
    top_dishes: [],
    price_changes: [],
  });
  expect(stats.by_employee).toEqual([
    { user_id: 3, full_name: 'Сотрудник 3', actual_kopecks: 0, order_count: 1 },
  ]);
});

it('keeps different price triples, handles missing actuals, and orders tied dishes deterministically', () => {
  const stats = demoStats(
    [
      plan({ items: [item, { ...item, dish_id: 2 }] }),
      plan({
        items: [
          { ...item, planned_price_kopecks: 43000 },
          { ...item, dish_id: 3, actual_price_kopecks: null, qty: 4 },
        ],
      }),
    ],
    users,
    period,
  );
  expect(stats.price_changes).toHaveLength(3);
  expect(
    stats.price_changes
      .filter((d) => d.dish_id === 1)
      .map((d) => d.planned_price_kopecks),
  ).toEqual([41000, 43000]);
  expect(stats.top_dishes.map((d) => d.dish_id)).toEqual([1, 3, 2]);
});
