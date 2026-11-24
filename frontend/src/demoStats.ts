import type { Plan, Stats, StatsFilter, User } from './types';

// Offline implementation of the period contract in docs/api.md.
export function demoStats(
  plans: Plan[],
  users: User[],
  filter: StatsFilter,
): Stats {
  const result: Stats = {
    from: filter.from,
    to: filter.to,
    total_planned_kopecks: 0,
    total_actual_kopecks: 0,
    delta_kopecks: 0,
    unavailable_count: 0,
    by_department: [],
    by_employee: [],
    top_dishes: [],
    price_changes: [],
  };
  for (const plan of plans) {
    if (
      plan.status !== 'included_in_order' ||
      plan.delivery_date < filter.from ||
      plan.delivery_date > filter.to
    )
      continue;
    const user = users.find((u) => u.id === plan.user_id)!;
    if (
      filter.department_id !== undefined &&
      user.department?.id !== filter.department_id
    )
      continue;

    let person = result.by_employee.find((u) => u.user_id === user.id);
    if (!person) {
      person = {
        user_id: user.id,
        full_name: user.full_name,
        actual_kopecks: 0,
        order_count: 0,
      };
      result.by_employee.push(person);
    }
    person.order_count++;
    let department = result.by_department.find(
      (d) => d.department_id === user.department?.id,
    );
    if (user.department && !department) {
      department = {
        department_id: user.department.id,
        name: user.department.name,
        actual_kopecks: 0,
        order_count: 0,
      };
      result.by_department.push(department);
    }
    if (department) department.order_count++;

    for (const item of plan.items) {
      if (item.unavailable) {
        result.unavailable_count++;
        continue;
      }
      const actual = (item.actual_price_kopecks ?? 0) * item.qty;
      result.total_planned_kopecks += item.planned_price_kopecks * item.qty;
      result.total_actual_kopecks += actual;
      person.actual_kopecks += actual;
      if (department) department.actual_kopecks += actual;
      let dish = result.top_dishes.find((d) => d.dish_id === item.dish_id);
      if (!dish) {
        dish = {
          dish_id: item.dish_id,
          name: item.name,
          qty: 0,
          actual_kopecks: 0,
        };
        result.top_dishes.push(dish);
      }
      dish.qty += item.qty;
      dish.actual_kopecks += actual;
      if (
        item.actual_price_kopecks !== null &&
        item.actual_price_kopecks !== item.planned_price_kopecks &&
        !result.price_changes.some(
          (d) =>
            d.dish_id === item.dish_id &&
            d.planned_price_kopecks === item.planned_price_kopecks &&
            d.actual_price_kopecks === item.actual_price_kopecks,
        )
      )
        result.price_changes.push({
          dish_id: item.dish_id,
          name: item.name,
          planned_price_kopecks: item.planned_price_kopecks,
          actual_price_kopecks: item.actual_price_kopecks,
        });
    }
  }
  const byName = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
  result.by_department.sort(
    (a, b) => byName(a.name, b.name) || a.department_id - b.department_id,
  );
  result.by_employee.sort(
    (a, b) => byName(a.full_name, b.full_name) || a.user_id - b.user_id,
  );
  result.top_dishes.sort(
    (a, b) =>
      b.qty - a.qty ||
      b.actual_kopecks - a.actual_kopecks ||
      a.dish_id - b.dish_id,
  );
  result.price_changes.sort(
    (a, b) =>
      byName(a.name, b.name) ||
      a.dish_id - b.dish_id ||
      a.planned_price_kopecks - b.planned_price_kopecks ||
      a.actual_price_kopecks - b.actual_price_kopecks,
  );
  result.delta_kopecks =
    result.total_actual_kopecks - result.total_planned_kopecks;
  return result;
}
