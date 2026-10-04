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
    is_active: true,
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

it('shows people and departments while settings are still loading', async () => {
  setup({ settings: () => new Promise(() => {}) });
  expect(
    await screen.findByRole('button', { name: 'Изменить Админ' }),
  ).toBeEnabled();
  expect(screen.getByLabelText('Новый отдел')).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: '+ Сотрудник' }));
  expect(screen.getByLabelText('Имя и фамилия')).toBeEnabled();
});

it('retries settings without blocking people or departments', async () => {
  const settings = vi
    .fn()
    .mockRejectedValueOnce(new Error('Временная ошибка'))
    .mockResolvedValue({
      cutoff_time: '15:30',
      timezone: 'Europe/Moscow',
      mealty_city: 'Москва',
      daily_limit_kopecks: null,
      catalog_sync_per_day: 2,
    });
  setup({ settings });
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Временная ошибка',
  );
  expect(screen.getByRole('button', { name: '+ Сотрудник' })).toBeEnabled();
  fireEvent.click(
    screen.getByRole('button', { name: 'Повторить загрузку настроек' }),
  );
  expect(await screen.findByLabelText('Закрытие приёма')).toHaveValue('15:30');
});

it('does not silently activate a user when the API omits their status', async () => {
  const saveUser = vi.fn().mockResolvedValue(undefined);
  setup({
    users: async () => [
      {
        id: 2,
        email: 'test@example.com',
        full_name: 'Тест',
        role: 'employee',
        department: null,
        daily_limit_kopecks: null,
      },
    ],
    saveUser,
  });
  expect(await screen.findByText('Не указан')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Изменить Тест' }));
  fireEvent.change(screen.getByLabelText('Имя и фамилия'), {
    target: { value: 'Новое имя' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить сотрудника' }));
  await waitFor(() => expect(saveUser).toHaveBeenCalledOnce());
  expect(saveUser.mock.calls[0][0]).not.toHaveProperty('is_active');
  expect(saveUser.mock.calls[0][0].full_name).toBe('Новое имя');
});

it('creates a user with the selected department, role, kopecks and inactive status', async () => {
  const saveUser = vi.fn().mockResolvedValue(undefined);
  setup({ saveUser });
  const add = screen.getByRole('button', { name: '+ Сотрудник' });
  await waitFor(() => expect(add).toBeEnabled());
  fireEvent.click(add);
  fireEvent.change(screen.getByLabelText('Имя и фамилия'), {
    target: { value: ' Новый сотрудник ' },
  });
  fireEvent.change(screen.getByLabelText('Почта'), {
    target: { value: 'new@example.com' },
  });
  fireEvent.change(screen.getByLabelText('Временный пароль'), {
    target: { value: 'temporary' },
  });
  fireEvent.change(screen.getByLabelText('Роль'), {
    target: { value: 'procurement' },
  });
  fireEvent.change(screen.getByLabelText('Отдел'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Лимит ₽ / день', { exact: true }), {
    target: { value: '700,50' },
  });
  fireEvent.click(screen.getByLabelText('Учётная запись активна'));
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить сотрудника' }));
  await waitFor(() =>
    expect(saveUser).toHaveBeenCalledWith(
      {
        email: 'new@example.com',
        password: 'temporary',
        full_name: 'Новый сотрудник',
        role: 'procurement',
        department_id: 1,
        daily_limit_kopecks: 70050,
        is_active: false,
      },
      undefined,
    ),
  );
  expect(await screen.findByText('Сотрудник сохранён.')).toBeVisible();
});

it.each([
  ['', null],
  ['0', 0],
  ['700,50', 70050],
])('saves the full settings object with limit %s', async (input, expected) => {
  const saveSettings = vi.fn().mockResolvedValue(undefined);
  setup({ saveSettings });
  fireEvent.change(await screen.findByLabelText('Общий лимит ₽ / день'), {
    target: { value: input },
  });
  fireEvent.change(screen.getByLabelText('Закрытие приёма'), {
    target: { value: '15:30' },
  });
  fireEvent.change(screen.getByLabelText('Город Mealty'), {
    target: { value: 'Санкт-Петербург' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }));
  await waitFor(() =>
    expect(saveSettings).toHaveBeenCalledWith({
      cutoff_time: '15:30',
      timezone: 'Europe/Moscow',
      mealty_city: 'Санкт-Петербург',
      daily_limit_kopecks: expected,
      catalog_sync_per_day: 2,
    }),
  );
});

it('retains settings after a rejected save and allows correction and retry', async () => {
  const saveSettings = vi
    .fn()
    .mockRejectedValueOnce(new Error('Сохранение не удалось'))
    .mockResolvedValue(undefined);
  setup({ saveSettings });
  fireEvent.change(await screen.findByLabelText('Общий лимит ₽ / день'), {
    target: { value: '123,456' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'точностью до копейки',
  );
  expect(saveSettings).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Общий лимит ₽ / день'), {
    target: { value: '123,45' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Сохранение не удалось',
  );
  expect(screen.getByLabelText('Общий лимит ₽ / день')).toHaveValue('123,45');
  expect(screen.queryByText('✓ Настройки сохранены')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }));
  expect(await screen.findByText('✓ Настройки сохранены')).toBeVisible();
});

it('does not allow editing a department assignment while departments failed to load', async () => {
  setup({
    departments: async () => {
      throw new Error('Отделы недоступны');
    },
  });
  expect(
    await screen.findByRole('button', { name: 'Изменить Админ' }),
  ).toBeDisabled();
  expect(screen.getByRole('button', { name: '+ Сотрудник' })).toBeDisabled();
  expect(
    await screen.findByRole('button', { name: 'Сохранить настройки' }),
  ).toBeEnabled();
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
