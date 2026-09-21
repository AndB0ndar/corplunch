import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { Catalog } from './Catalog';
import { SessionContext } from '../session';
import { demoApi } from '../demo';
import { ApiError } from '../api';
import { shiftDate, today } from '../format';
import type { AppApi, Dish, Plan } from '../types';

const date = shiftDate(today(), 2);
const dish: Dish = {
  id: 1,
  source: 'mealty',
  external_id: '875',
  seller_product_id: null,
  name: 'Ньокки',
  subtitle: '',
  description: null,
  category: 'main_dish',
  price_kopecks: 42500,
  old_price_kopecks: null,
  weight_g: null,
  proteins: null,
  fats: null,
  carbs: null,
  calories: null,
  image_url: null,
  available: true,
};
const emptyPlan: Plan = {
  id: null,
  user_id: 1,
  delivery_date: date,
  status: 'draft',
  editable: true,
  planned_total_kopecks: 0,
  actual_total_kopecks: null,
  items: [],
};
const clients: QueryClient[] = [];
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
  vi.restoreAllMocks();
});
function setup(overrides: Partial<AppApi> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  const api: AppApi = {
    ...demoApi,
    catalog: async () => [dish],
    plan: async () => emptyPlan,
    ...overrides,
  };
  render(
    <QueryClientProvider client={client}>
      <SessionContext.Provider
        value={{
          api,
          user: {
            id: 1,
            email: 'test@example.com',
            full_name: 'Тест',
            role: 'employee',
            department: null,
            daily_limit_kopecks: null,
          },
          demo: false,
          logout: vi.fn(),
        }}
      >
        <Catalog />
      </SessionContext.Provider>
    </QueryClientProvider>,
  );
  return client;
}
it('shows the authoritative saved composition after cutoff rejects a dirty draft', async () => {
  let closed = false;
  setup({
    plan: async () =>
      closed
        ? {
            ...emptyPlan,
            status: 'included_in_order',
            editable: false,
            actual_total_kopecks: 0,
          }
        : emptyPlan,
    savePlan: async () => {
      closed = true;
      throw new ApiError(403, 'Приём заказов закрыт.');
    },
  });
  fireEvent.click(
    await screen.findByRole('button', { name: 'Добавить Ньокки' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить план' }));
  await screen.findByText('Приём заказов закрыт.');
  await waitFor(() =>
    expect(
      within(screen.getByRole('complementary')).queryByText('Ньокки'),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.queryByText('Есть несохранённые изменения'),
  ).not.toBeInTheDocument();
});
it('keeps the date fixed while the plan is saving', async () => {
  let complete!: (plan: Plan) => void;
  setup({
    savePlan: () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  });
  fireEvent.click(
    await screen.findByRole('button', { name: 'Добавить Ньокки' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить план' }));
  await screen.findByRole('button', { name: 'Сохраняем…' });
  expect(screen.getByLabelText('Дата доставки')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Следующий день' })).toBeDisabled();
  await act(async () => complete(emptyPlan));
});
it('preserves the editable draft after a limit error so it can be corrected', async () => {
  setup({
    savePlan: async () => {
      throw new ApiError(422, 'Превышен дневной лимит.');
    },
  });
  fireEvent.click(
    await screen.findByRole('button', { name: 'Добавить Ньокки' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить план' }));
  await screen.findByText('Превышен дневной лимит.');
  expect(
    within(screen.getByRole('complementary')).getByText('Ньокки'),
  ).toBeInTheDocument();
  expect(screen.getByText('Есть несохранённые изменения')).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: 'Уменьшить Ньокки' }),
  ).toBeEnabled();
});
it('uses the same current draft price in the line and total even when editing has closed', async () => {
  setup({
    plan: async () => ({
      ...emptyPlan,
      editable: false,
      planned_total_kopecks: 41000,
      items: [
        {
          dish_id: 1,
          name: 'Ньокки',
          qty: 1,
          planned_price_kopecks: 41000,
          actual_price_kopecks: null,
          unavailable: false,
        },
      ],
    }),
  });
  await screen.findByRole('heading', {
    name: `План на ${new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(new Date(`${date}T12:00:00Z`))}`,
  });
  const panel = within(screen.getByRole('complementary'));
  expect(panel.queryByText(/^410\s₽$/)).not.toBeInTheDocument();
  expect(panel.getAllByText(/^425\s₽$/)).toHaveLength(2);
});
