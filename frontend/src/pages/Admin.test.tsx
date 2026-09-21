import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { Admin } from './Admin';
import { SessionContext } from '../session';
import { demoApi } from '../demo';
import type { AppApi } from '../types';

const clients: QueryClient[] = [];
afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
});
function setup(overrides: Partial<AppApi>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  clients.push(client);
  const user = {
    id: 1,
    email: 'admin@example.com',
    full_name: 'Админ',
    role: 'admin' as const,
    department: null,
    daily_limit_kopecks: null,
  };
  const api: AppApi = {
    ...demoApi,
    users: async () => [user],
    departments: async () => [{ id: 1, name: 'Разработка' }],
    settings: async () => ({
      cutoff_time: '16:00',
      timezone: 'Europe/Moscow',
      mealty_city: 'Москва',
      daily_limit_kopecks: null,
      catalog_sync_per_day: 2,
    }),
    ...overrides,
  };
  render(
    <QueryClientProvider client={client}>
      <SessionContext.Provider
        value={{ api, user, demo: false, logout: vi.fn() }}
      >
        <Admin />
      </SessionContext.Provider>
    </QueryClientProvider>,
  );
}
it('prevents switching users and changing fields while a user is saving', async () => {
  let complete!: () => void;
  setup({
    saveUser: () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  });
  fireEvent.click(
    await screen.findByRole('button', { name: 'Изменить Админ' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить сотрудника' }));
  await screen.findByRole('button', { name: 'Сохраняем…' });
  expect(screen.getByLabelText('Имя и фамилия')).toBeDisabled();
  expect(screen.getByRole('button', { name: '+ Сотрудник' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Изменить Админ' })).toBeDisabled();
  await act(async () => complete());
});
it('prevents starting another department edit before a save completes', async () => {
  let complete!: () => void;
  setup({
    saveDepartment: () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  });
  const input = await screen.findByLabelText('Новый отдел');
  fireEvent.change(input, { target: { value: 'QA' } });
  fireEvent.click(screen.getByRole('button', { name: 'Добавить отдел' }));
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Добавить отдел' }),
    ).toBeDisabled(),
  );
  expect(input).toBeDisabled();
  expect(
    screen.getByRole('button', { name: /Разработка — изменить отдел/ }),
  ).toBeDisabled();
  await act(async () => complete());
});
it('does not allow unsent settings changes during a pending save', async () => {
  let complete!: () => void;
  setup({
    saveSettings: () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  });
  fireEvent.click(
    await screen.findByRole('button', { name: 'Сохранить настройки' }),
  );
  await screen.findByRole('button', { name: 'Сохраняем…' });
  expect(screen.getByLabelText('Город Mealty')).toBeDisabled();
  expect(screen.getByLabelText('Закрытие приёма')).toBeDisabled();
  await act(async () => complete());
});
