import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { liveApi } from './api';
import { demoApi, demoAccounts, resetDemo } from './demo';
import { getToken, setToken } from './token';
import { roles } from './format';
import { ErrorNotice, FoodArt, Loading } from './components';
import { SessionContext } from './session';
import { Catalog } from './pages/Catalog';
import { Orders } from './pages/Orders';
import { Statistics } from './pages/Statistics';
import { Admin } from './pages/Admin';

const demoAllowed =
  import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEMO === 'true';
type Mode = 'live' | 'demo' | null;
export default function App() {
  const client = useQueryClient();
  const [mode, setMode] = useState<Mode>(() =>
    demoAllowed && sessionStorage.getItem('corplunch.mode') === 'demo'
      ? 'demo'
      : getToken()
        ? 'live'
        : null,
  );
  const api = mode === 'demo' ? demoApi : liveApi;
  const profile = useQuery({
    queryKey: ['me', mode],
    queryFn: () => api.me(),
    enabled: !!mode,
    retry: false,
  });
  function logout() {
    setToken(null);
    sessionStorage.removeItem('corplunch.mode');
    sessionStorage.removeItem('corplunch.demo.user');
    setMode(null);
    client.clear();
  }
  useEffect(() => {
    const expire = () => {
      setMode(null);
      client.clear();
    };
    window.addEventListener('corplunch:unauthorized', expire);
    return () => window.removeEventListener('corplunch:unauthorized', expire);
  }, [client]);
  async function login(email: string, password: string, demo: boolean) {
    const next = demo ? 'demo' : 'live';
    await (demo ? demoApi : liveApi).login(email, password);
    client.clear();
    sessionStorage.setItem('corplunch.mode', next);
    setMode(next);
  }
  if (!mode) return <Login login={login} />;
  if (profile.isPending) return <Loading />;
  if (!profile.data)
    return (
      <main className="login-card">
        <ErrorNotice error={profile.error} />
        <button onClick={logout}>Вернуться ко входу</button>
      </main>
    );
  const user = profile.data;
  const employee = user.role === 'employee';
  const home = employee ? '/catalog' : '/orders';
  return (
    <SessionContext.Provider
      value={{ api, user, demo: mode === 'demo', logout }}
    >
      {mode === 'demo' && (
        <div className="demo-bar">
          <span>Деморежим · учебные данные в этом браузере</span>
          <button
            onClick={() => {
              if (
                window.confirm(
                  'Сбросить все учебные планы, заказы и настройки?',
                )
              ) {
                resetDemo();
                logout();
              }
            }}
          >
            Сбросить демо
          </button>
        </div>
      )}
      <header className="header">
        <NavLink to={home} className="brand">
          <span className="brand-icon">
            cl<span>↗</span>
          </span>
          CorpLunch<span className="brand-note">обед в хорошей компании</span>
        </NavLink>
        <nav aria-label="Основная навигация">
          {employee ? (
            <NavLink to="/catalog">Меню и план</NavLink>
          ) : (
            <>
              <NavLink to="/orders">Сводка дня</NavLink>
              <NavLink to="/stats">Статистика</NavLink>
            </>
          )}
          {user.role === 'admin' && <NavLink to="/admin">Управление</NavLink>}
        </nav>
        <div className="profile">
          <span className="avatar">{user.full_name.slice(0, 1)}</span>
          <span>
            <b>{user.full_name}</b>
            <small>{roles[user.role]}</small>
          </span>
          <button
            className="quiet"
            onClick={() => {
              if (
                window.dispatchEvent(
                  new Event('corplunch:before-logout', { cancelable: true }),
                )
              )
                logout();
            }}
          >
            Выйти
          </button>
        </div>
      </header>
      <main className="workspace">
        <Routes>
          <Route
            path="/catalog"
            element={employee ? <Catalog /> : <Navigate to={home} replace />}
          />
          <Route
            path="/orders"
            element={!employee ? <Orders /> : <Navigate to={home} replace />}
          />
          <Route
            path="/stats"
            element={
              !employee ? <Statistics /> : <Navigate to={home} replace />
            }
          />
          <Route
            path="/admin"
            element={
              user.role === 'admin' ? <Admin /> : <Navigate to={home} replace />
            }
          />
          <Route path="*" element={<Navigate to={home} replace />} />
        </Routes>
      </main>
      <footer className="footer">
        <span>CorpLunch · забота об обеде, без лишней суеты</span>
        <span>Время офиса — Москва</span>
      </footer>
    </SessionContext.Provider>
  );
}
function Login({
  login,
}: {
  login: (email: string, password: string, demo: boolean) => Promise<void>;
}) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(
    emailValue = email,
    passwordValue = password,
    demo = false,
  ) {
    setError(null);
    setBusy(true);
    try {
      await login(emailValue, passwordValue, demo);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Не удалось войти.'));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-layout">
      <section className="login-story">
        <div className="brand">
          <span className="brand-icon">cl↗</span>CorpLunch
        </div>
        <div>
          <p className="eyebrow">ВАШ ОБЕД. ВАШ ПЛАН.</p>
          <h1>
            Хороший день
            <br />
            начинается
            <br />с обеда.
          </h1>
          <p>
            Выбирайте любимое заранее.
            <br />
            Мы соберём заказы офиса в один список.
          </p>
          <FoodArt category="salad" id={1} />
        </div>
        <small>Планируйте спокойно. Обедайте вместе.</small>
      </section>
      <section className="login-panel">
        <form
          className="login-card"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <p className="eyebrow">ДОБРО ПОЖАЛОВАТЬ</p>
          <h2>Войдём и выберем обед</h2>
          <p className="muted">Используйте рабочую почту и пароль.</p>
          <label>
            Рабочая почта
            <input
              type="email"
              autoComplete="username"
              placeholder="name@company.ru"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <ErrorNotice error={error} />
          <button className="primary full" disabled={busy}>
            {busy ? 'Входим…' : 'Войти →'}
          </button>
          {demoAllowed && (
            <div className="demo-login">
              <p>Посмотреть без сервера</p>
              <small>Демо-учётки · пароль совпадает с частью почты до @</small>
              <div className="demo-buttons">
                {demoAccounts.map((a, i) => (
                  <button
                    disabled={busy}
                    type="button"
                    key={a}
                    onClick={() => void submit(`${a}@kis.local`, a, true)}
                  >
                    {
                      ['Сотрудник', 'Сотрудник 2', 'Закупки', 'Администратор'][
                        i
                      ]
                    }
                  </button>
                ))}
              </div>
              <small>Учебные данные не отправляются на сервер.</small>
            </div>
          )}
        </form>
      </section>
    </main>
  );
}
