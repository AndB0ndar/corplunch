import { afterEach, describe, expect, it, vi } from 'vitest';
import { liveApi, request } from './api';
import { getToken, setToken } from './token';
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});
describe('HTTP contract', () => {
  it('does not let a delayed 401 from an old session clear the new token', async () => {
    let complete!: (response: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            complete = resolve;
          }),
      ),
    );
    setToken('old-session');
    const pending = liveApi.me();
    setToken('new-session');
    complete(new Response('{}', { status: 401 }));
    await expect(pending).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBe('new-session');
  });
  it('sends Bearer without cookies and exact snake_case plan payload', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetch);
    setToken('test-token');
    await liveApi.savePlan('2026-09-20', [{ dish_id: 12, qty: 2 }]);
    const [path, init] = fetch.mock.calls[0];
    expect(path).toBe('/api/plans/2026-09-20');
    expect(init.credentials).toBe('omit');
    expect(init.headers.get('Authorization')).toBe('Bearer test-token');
    expect(JSON.parse(init.body)).toEqual({ items: [{ dish_id: 12, qty: 2 }] });
  });
  it('clears an expired session', async () => {
    setToken('expired');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":"Not authenticated"}', { status: 401 }),
        ),
    );
    const listener = vi.fn();
    window.addEventListener('corplunch:unauthorized', listener);
    await expect(liveApi.me()).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener('corplunch:unauthorized', listener);
  });
  it('shows validation and quota errors without object-string garbage', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":[{"msg":"required"}]}', { status: 422 }),
        ),
    );
    await expect(request('/admin/users')).rejects.toThrow(
      'Проверьте введённые данные',
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 429 })),
    );
    await expect(liveApi.sync()).rejects.toThrow('Дневной лимит');
  });
  it('does not include email or an empty password in PATCH', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetch);
    await liveApi.saveUser(
      {
        email: 'e@example.com',
        password: '',
        full_name: 'Иван',
        role: 'employee',
        department_id: null,
        daily_limit_kopecks: null,
        is_active: true,
      },
      10,
    );
    const input = JSON.parse(fetch.mock.calls[0][1].body);
    expect(input).not.toHaveProperty('email');
    expect(input).not.toHaveProperty('password');
  });
  it('returns downloaded bytes instead of trying to parse JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('external_id,name\n875,Ньокки', {
          headers: { 'Content-Type': 'text/csv' },
        }),
      ),
    );
    const blob = await liveApi.exportOrder('2026-09-20', 'csv');
    expect(blob.size).toBeGreaterThan(0);
  });
});
