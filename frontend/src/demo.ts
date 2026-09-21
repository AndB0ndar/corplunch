// Browser-only teaching data. Never used as a fallback for a failed HTTP request.
import { ApiError } from './api';
import { shiftDate, today } from './format';
import type {
  AppApi,
  Department,
  Dish,
  Order,
  Plan,
  Settings,
  Stats,
  User,
} from './types';

type State = {
  users: User[];
  departments: Department[];
  settings: Settings;
  dishes: Dish[];
  plans: Record<string, Plan>;
  orders: Record<string, Order>;
  syncDay: string;
  syncCount: number;
};
const key = 'corplunch.demo.v1';
export const demoAccounts = [
  'employee',
  'employee2',
  'procurement',
  'admin',
] as const;
function initialState(): State {
  const departments = [
    { id: 1, name: 'Разработка' },
    { id: 2, name: 'Маркетинг' },
    { id: 3, name: 'Закупки' },
  ];
  const names = [
    'Александр Иванов',
    'Анна Смирнова',
    'Мария Петрова',
    'Администратор',
  ];
  const dishes: Dish[] = [
    [
      'Картофельные ньокки',
      'с грибами и сливочным соусом',
      'main_dish',
      41000,
      300,
    ],
    ['Куриная грудка', 'с булгуром и овощами', 'main_dish', 39000, 280],
    ['Тыквенный суп', 'со сливками и семечками', 'soup', 24000, 300],
    ['Салат с печёной свёклой', 'сыром и свежей зеленью', 'salad', 29000, 180],
    ['Сырники', 'со сметаной и ягодным соусом', 'breakfast', 26000, 180],
    [
      'Чиабатта с индейкой',
      'с моцареллой и сладким перцем',
      'sandwich',
      32000,
      250,
    ],
    ['Морковный торт', 'с нежным сливочным кремом', 'dessert', 22000, 130],
    ['Морс из клюквы', 'освежающий, с лёгкой кислинкой', 'drink', 12000, 300],
  ].map((row, i) => ({
    id: i + 1,
    source: 'mealty',
    external_id: String(875 + i),
    seller_product_id: null,
    name: String(row[0]),
    subtitle: String(row[1]),
    category: String(row[2]),
    price_kopecks: Number(row[3]),
    weight_g: Number(row[4]),
    old_price_kopecks: i === 0 ? 45000 : null,
    description:
      'Учебная карточка для проверки интерфейса. Состав уточняется в каталоге поставщика.',
    proteins: 12,
    fats: 9,
    carbs: 24,
    calories: 225,
    image_url: null,
    available: true,
  }));
  return {
    departments,
    users: demoAccounts.map((account, i) => ({
      id: i + 1,
      email: `${account}@kis.local`,
      full_name: names[i],
      role: i < 2 ? 'employee' : i === 2 ? 'procurement' : 'admin',
      department: departments[i === 0 ? 0 : i === 1 ? 1 : 2],
      daily_limit_kopecks: null,
      is_active: true,
    })),
    settings: {
      cutoff_time: '16:00',
      timezone: 'Europe/Moscow',
      mealty_city: 'Москва',
      daily_limit_kopecks: null,
      catalog_sync_per_day: 2,
    },
    dishes,
    plans: {},
    orders: {},
    syncDay: today(),
    syncCount: 0,
  };
}
function load(): State {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return JSON.parse(raw) as State;
  } catch {
    /* Fresh demo after damaged browser storage. */
  }
  return initialState();
}
let state = load();
const persist = () => localStorage.setItem(key, JSON.stringify(state));
const clone = <T>(value: T): T => structuredClone(value);
const fail = (code: number, message: string): never => {
  throw new ApiError(code, message);
};
export function resetDemo() {
  state = initialState();
  persist();
  sessionStorage.removeItem('corplunch.demo.user');
}
function current(): User {
  const user = state.users.find(
    (u) => u.id === Number(sessionStorage.getItem('corplunch.demo.user')),
  );
  if (!user || !user.is_active) return fail(401, 'Войдите в деморежим снова.');
  return user;
}
function authorize(admin = false) {
  const u = current();
  if (admin ? u.role !== 'admin' : u.role === 'employee')
    fail(403, 'Недостаточно прав.');
}
export function beforeCutoff(date: string, time: string, now = Date.now()) {
  return now < Date.parse(`${shiftDate(date, -1)}T${time}:00+03:00`);
}
function readPlan(date: string, userId: number): Plan {
  const plan = clone(
    state.plans[`${userId}:${date}`] ?? {
      id: null,
      user_id: userId,
      delivery_date: date,
      status: 'draft',
      editable: true,
      planned_total_kopecks: 0,
      actual_total_kopecks: null,
      items: [],
    },
  );
  plan.editable =
    plan.status === 'draft' &&
    !state.orders[date] &&
    beforeCutoff(date, state.settings.cutoff_time);
  return plan;
}
function plansOn(date: string) {
  return Object.values(state.plans).filter((p) => p.delivery_date === date);
}
function summarize(date: string, plans: Plan[]): Order {
  const result: Order = {
    delivery_date: date,
    status: 'collecting',
    totals: {
      planned_kopecks: 0,
      actual_kopecks: 0,
      delta_kopecks: 0,
      unavailable_count: 0,
    },
    items: [],
    by_employee: [],
  };
  for (const plan of plans) {
    const user = state.users.find((u) => u.id === plan.user_id)!;
    let actual = 0;
    for (const item of plan.items) {
      result.totals.planned_kopecks += item.planned_price_kopecks * item.qty;
      if (item.unavailable) {
        result.totals.unavailable_count++;
        continue;
      }
      const price = item.actual_price_kopecks ?? item.planned_price_kopecks;
      actual += price * item.qty;
      const existing = result.items.find((i) => i.dish_id === item.dish_id);
      if (existing) {
        existing.qty += item.qty;
        existing.line_total_kopecks += price * item.qty;
      } else
        result.items.push({
          dish_id: item.dish_id,
          external_id: state.dishes.find((d) => d.id === item.dish_id)!
            .external_id,
          name: item.name,
          qty: item.qty,
          unit_price_kopecks: price,
          line_total_kopecks: price * item.qty,
        });
    }
    result.totals.actual_kopecks += actual;
    result.by_employee.push({
      user_id: user.id,
      full_name: user.full_name,
      department_id: user.department?.id ?? null,
      department_name: user.department?.name ?? null,
      actual_total_kopecks: actual,
      unavailable_count: plan.items.filter((i) => i.unavailable).length,
    });
  }
  result.totals.delta_kopecks =
    result.totals.actual_kopecks - result.totals.planned_kopecks;
  return result;
}
export const demoApi: AppApi = {
  async login(email, password) {
    const account = demoAccounts.find(
      (a) => email === `${a}@kis.local` && password === a,
    );
    const user = state.users.find((u) => u.email === email && u.is_active);
    if (!account || !user) fail(401, 'Неверная почта или пароль демо-учётки.');
    sessionStorage.setItem('corplunch.demo.user', String(user!.id));
  },
  async me() {
    return clone(current());
  },
  async catalog() {
    current();
    return clone(state.dishes);
  },
  async plan(date, userId) {
    const user = current();
    if (userId !== undefined && userId !== user.id) authorize();
    return readPlan(date, userId ?? user.id);
  },
  async savePlan(date, items) {
    const user = current();
    if (user.role !== 'employee')
      fail(403, 'Изменять план может только сотрудник.');
    const plan = readPlan(date, user.id);
    if (!plan.editable)
      fail(
        403,
        'Приём заказов на эту дату закрыт. Изменить состав уже нельзя.',
      );
    plan.items = items.map((i) => {
      const dish = state.dishes.find((d) => d.id === i.dish_id && d.available);
      if (!dish) return fail(409, 'Блюдо больше недоступно. Обновите каталог.');
      if (!Number.isInteger(i.qty) || i.qty < 1)
        return fail(422, 'Количество должно быть целым и положительным.');
      return {
        dish_id: dish.id,
        name: dish.name,
        qty: i.qty,
        planned_price_kopecks: dish.price_kopecks,
        actual_price_kopecks: null,
        unavailable: false,
      };
    });
    plan.planned_total_kopecks = plan.items.reduce(
      (sum, i) => sum + i.qty * i.planned_price_kopecks,
      0,
    );
    const limit =
      user.daily_limit_kopecks ?? state.settings.daily_limit_kopecks;
    if (limit !== null && plan.planned_total_kopecks > limit)
      fail(422, 'Превышен дневной лимит. Уберите часть блюд.');
    plan.id = user.id;
    state.plans[`${user.id}:${date}`] = plan;
    persist();
    return clone(plan);
  },
  async order(date) {
    authorize();
    return clone(state.orders[date] ?? summarize(date, plansOn(date)));
  },
  async cutoff(date) {
    authorize();
    if (state.orders[date]) return;
    const plans = plansOn(date);
    if (!plans.some((p) => p.items.length))
      fail(400, 'На эту дату пока нет заказов.');
    // Deterministic teaching scenario: first dish rises by 15 ₽; salad disappears.
    for (const plan of plans) {
      plan.editable = false;
      plan.status = 'included_in_order';
      plan.items.forEach((i) => {
        const d = state.dishes.find((d) => d.id === i.dish_id)!;
        i.unavailable = d.id === 4 || !d.available;
        i.actual_price_kopecks = i.unavailable
          ? null
          : d.price_kopecks + (d.id === 1 ? 1500 : 0);
      });
      plan.actual_total_kopecks = plan.items.reduce(
        (sum, i) => sum + (i.actual_price_kopecks ?? 0) * i.qty,
        0,
      );
    }
    state.orders[date] = { ...summarize(date, plans), status: 'locked' };
    persist();
  },
  async place(date) {
    authorize();
    const order = state.orders[date];
    if (!order) return fail(403, 'Сначала закройте приём заказов.');
    order.status = 'placed';
    persist();
  },
  async sync() {
    authorize();
    if (state.syncDay !== today()) {
      state.syncDay = today();
      state.syncCount = 0;
    }
    if (state.syncCount >= state.settings.catalog_sync_per_day)
      fail(429, 'Дневной лимит обновлений каталога исчерпан.');
    state.syncCount++;
    persist();
  },
  async exportOrder(date, format) {
    authorize();
    const order = state.orders[date];
    if (!order) return fail(403, 'Сначала закройте приём заказов.');
    const { exportDemo } = await import('./demoExport');
    const blob = exportDemo(order, format);
    if (order.status !== 'placed') order.status = 'exported';
    persist();
    return blob;
  },
  async stats(filter) {
    authorize();
    const result: Stats = {
      ...filter,
      total_planned_kopecks: 0,
      total_actual_kopecks: 0,
      delta_kopecks: 0,
      unavailable_count: 0,
      by_department: [],
      by_employee: [],
      top_dishes: [],
      price_changes: [],
    };
    for (const plan of Object.values(state.plans).filter(
      (p) =>
        p.status !== 'draft' &&
        p.delivery_date >= filter.from &&
        p.delivery_date <= filter.to,
    )) {
      const user = state.users.find((u) => u.id === plan.user_id)!;
      if (
        filter.department_id !== undefined &&
        user.department?.id !== filter.department_id
      )
        continue;
      result.total_planned_kopecks += plan.planned_total_kopecks;
      result.total_actual_kopecks += plan.actual_total_kopecks ?? 0;
      if (user.department) {
        let row = result.by_department.find(
          (d) => d.department_id === user.department!.id,
        );
        if (!row) {
          row = {
            department_id: user.department.id,
            name: user.department.name,
            actual_kopecks: 0,
            order_count: 0,
          };
          result.by_department.push(row);
        }
        row.actual_kopecks += plan.actual_total_kopecks ?? 0;
        row.order_count++;
      }
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
      person.actual_kopecks += plan.actual_total_kopecks ?? 0;
      person.order_count++;
      for (const item of plan.items) {
        if (item.unavailable) {
          result.unavailable_count++;
          continue;
        }
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
        dish.actual_kopecks += (item.actual_price_kopecks ?? 0) * item.qty;
        if (
          item.actual_price_kopecks !== null &&
          item.actual_price_kopecks !== item.planned_price_kopecks
        )
          result.price_changes.push({
            dish_id: item.dish_id,
            name: item.name,
            planned_price_kopecks: item.planned_price_kopecks,
            actual_price_kopecks: item.actual_price_kopecks,
          });
      }
    }
    result.delta_kopecks =
      result.total_actual_kopecks - result.total_planned_kopecks;
    result.top_dishes.sort((a, b) => b.qty - a.qty);
    return result;
  },
  async departments() {
    authorize(true);
    return clone(state.departments);
  },
  async saveDepartment(name, id) {
    authorize(true);
    if (!name.trim()) fail(422, 'Введите название отдела.');
    if (id === undefined)
      state.departments.push({
        id: Math.max(0, ...state.departments.map((d) => d.id)) + 1,
        name: name.trim(),
      });
    else {
      const d = state.departments.find((d) => d.id === id)!;
      d.name = name.trim();
      state.users.forEach((u) => {
        if (u.department?.id === id) u.department.name = d.name;
      });
    }
    persist();
  },
  async users() {
    authorize(true);
    return clone(state.users);
  },
  async saveUser(input, id) {
    authorize(true);
    if (id === undefined && state.users.some((u) => u.email === input.email))
      fail(409, 'Эта почта уже используется.');
    const user: User = {
      id: id ?? Math.max(...state.users.map((u) => u.id)) + 1,
      email: input.email,
      full_name: input.full_name,
      role: input.role,
      department:
        state.departments.find((d) => d.id === input.department_id) ?? null,
      daily_limit_kopecks: input.daily_limit_kopecks,
      is_active: input.is_active,
    };
    if (id === undefined) state.users.push(user);
    else state.users = state.users.map((u) => (u.id === id ? user : u));
    persist();
  },
  async settings() {
    authorize(true);
    return clone(state.settings);
  },
  async saveSettings(input) {
    authorize(true);
    state.settings = clone(input);
    persist();
  },
};
