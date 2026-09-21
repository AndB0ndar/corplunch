export type Role = 'employee' | 'procurement' | 'admin';
export type Department = { id: number; name: string };
export type User = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  department: Department | null;
  daily_limit_kopecks: number | null;
  is_active?: boolean;
};
export type UserInput = {
  email: string;
  password: string;
  full_name: string;
  role: Role;
  department_id: number | null;
  daily_limit_kopecks: number | null;
  is_active: boolean;
};
export type Settings = {
  cutoff_time: string;
  timezone: string;
  mealty_city: string;
  daily_limit_kopecks: number | null;
  catalog_sync_per_day: number;
};
export type Dish = {
  id: number;
  source: string;
  external_id: string;
  seller_product_id: string | null;
  name: string;
  subtitle: string;
  description: string | null;
  category: string;
  price_kopecks: number;
  old_price_kopecks: number | null;
  weight_g: number | null;
  proteins: number | null;
  fats: number | null;
  carbs: number | null;
  calories: number | null;
  image_url: string | null;
  available: boolean;
};
export type PlanItem = {
  dish_id: number;
  name: string;
  qty: number;
  planned_price_kopecks: number;
  actual_price_kopecks: number | null;
  unavailable: boolean;
};
export type Plan = {
  id: number | null;
  user_id: number;
  delivery_date: string;
  status: 'draft' | 'locked' | 'priced' | 'included_in_order';
  editable: boolean;
  planned_total_kopecks: number;
  actual_total_kopecks: number | null;
  items: PlanItem[];
};
export type Order = {
  delivery_date: string;
  status: 'collecting' | 'locked' | 'exported' | 'placed';
  totals: {
    planned_kopecks: number;
    actual_kopecks: number;
    delta_kopecks: number;
    unavailable_count: number;
  };
  items: {
    dish_id: number;
    external_id: string;
    name: string;
    qty: number;
    unit_price_kopecks: number;
    line_total_kopecks: number;
  }[];
  by_employee: {
    user_id: number;
    full_name: string;
    department_id: number | null;
    department_name: string | null;
    actual_total_kopecks: number;
    unavailable_count: number;
  }[];
};
export type Stats = {
  from: string;
  to: string;
  total_planned_kopecks: number;
  total_actual_kopecks: number;
  delta_kopecks: number;
  unavailable_count: number;
  by_department: {
    department_id: number;
    name: string;
    actual_kopecks: number;
    order_count: number;
  }[];
  by_employee: {
    user_id: number;
    full_name: string;
    actual_kopecks: number;
    order_count: number;
  }[];
  top_dishes: {
    dish_id: number;
    name: string;
    qty: number;
    actual_kopecks: number;
  }[];
  price_changes: {
    dish_id: number;
    name: string;
    planned_price_kopecks: number;
    actual_price_kopecks: number;
  }[];
};
export type StatsFilter = { from: string; to: string; department_id?: number };
export interface AppApi {
  login(email: string, password: string): Promise<void>;
  me(): Promise<User>;
  catalog(): Promise<Dish[]>;
  plan(date: string, userId?: number): Promise<Plan>;
  savePlan(
    date: string,
    items: { dish_id: number; qty: number }[],
  ): Promise<Plan>;
  order(date: string): Promise<Order>;
  cutoff(date: string): Promise<void>;
  place(date: string): Promise<void>;
  sync(): Promise<void>;
  exportOrder(date: string, format: 'csv' | 'xlsx'): Promise<Blob>;
  stats(filter: StatsFilter): Promise<Stats>;
  departments(): Promise<Department[]>;
  saveDepartment(name: string, id?: number): Promise<void>;
  users(): Promise<User[]>;
  saveUser(input: UserInput, id?: number): Promise<void>;
  settings(): Promise<Settings>;
  saveSettings(input: Settings): Promise<void>;
}
