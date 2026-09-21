import { getToken, setToken } from './token';
import type { AppApi } from './types';

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
const messages: Record<number, string> = {
  401: 'Сессия завершена или неверная почта / пароль. Войдите снова.',
  403: 'Действие недоступно: проверьте права и время закрытия приёма.',
  404: 'Запись не найдена. Обновите страницу.',
  409: 'Данные изменились. Обновите страницу и проверьте состав.',
  422: 'Проверьте введённые данные и дневной лимит.',
  429: 'Дневной лимит обновлений каталога исчерпан. Попробуйте завтра.',
  502: 'Mealty временно недоступен. Последний каталог сохранён.',
};
export async function request<T>(
  path: string,
  init?: RequestInit,
  blob = false,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Accept', blob ? '*/*' : 'application/json');
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers,
      credentials: 'omit',
    });
  } catch {
    throw new ApiError(
      0,
      'Нет связи с сервером. Проверьте подключение и попробуйте снова.',
    );
  }
  if (!response.ok) {
    const responseBody: unknown = await response.json().catch(() => null);
    const detail =
      responseBody &&
      typeof responseBody === 'object' &&
      'detail' in responseBody
        ? responseBody.detail
        : null;
    if (
      response.status === 401 &&
      path !== '/auth/login' &&
      token === getToken()
    ) {
      setToken(null);
      window.dispatchEvent(new Event('corplunch:unauthorized'));
    }
    throw new ApiError(
      response.status,
      typeof detail === 'string' && /[а-яё]/i.test(detail)
        ? detail
        : (messages[response.status] ??
            'Не удалось выполнить запрос. Попробуйте снова.'),
    );
  }

  if (blob) return (await response.blob()) as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
const body = (method: string, value?: unknown) => ({
  method,
  ...(value === undefined ? {} : { body: JSON.stringify(value) }),
});
export const liveApi: AppApi = {
  async login(email, password) {
    const result = await request<{ access_token: string }>(
      '/auth/login',
      body('POST', { email, password }),
    );
    setToken(result.access_token);
  },
  me: () => request('/me'),
  catalog: () => request('/catalog?available_only=false'),
  plan: (date, userId) =>
    request(
      `/plans/${date}${userId === undefined ? '' : `?user_id=${userId}`}`,
    ),
  savePlan: (date, items) => request(`/plans/${date}`, body('PUT', { items })),
  order: (date) => request(`/orders/${date}`),
  cutoff: (date) => request(`/orders/${date}/cutoff`, body('POST')),
  place: (date) => request(`/orders/${date}/place`, body('POST')),
  sync: () => request('/catalog/sync', body('POST')),
  exportOrder: (date, format) =>
    request(`/orders/${date}/export.${format}`, undefined, true),
  stats: (filter) =>
    request(
      `/stats/summary?${new URLSearchParams(Object.entries(filter).map(([key, value]) => [key, String(value)]))}`,
    ),
  departments: () => request('/admin/departments'),
  saveDepartment: (name, id) =>
    request(
      `/admin/departments${id === undefined ? '' : `/${id}`}`,
      body(id === undefined ? 'POST' : 'PATCH', { name }),
    ),
  users: () => request('/admin/users'),
  saveUser: (input, id) => {
    const { email, password, ...fields } = input;
    return request(
      `/admin/users${id === undefined ? '' : `/${id}`}`,
      body(id === undefined ? 'POST' : 'PATCH', {
        ...fields,
        ...(id === undefined ? { email } : {}),
        ...(password ? { password } : {}),
      }),
    );
  },
  settings: () => request('/admin/settings'),
  saveSettings: (input) => request('/admin/settings', body('PUT', input)),
};
