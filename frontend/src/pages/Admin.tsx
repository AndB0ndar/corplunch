import { useAction } from '../useAction';
import { useState } from 'react';
import { useIsMutating, useQuery } from '@tanstack/react-query';
import { Empty, ErrorNotice, Loading } from '../components';
import { money, roles, rublesToKopecks } from '../format';
import { useSession } from '../session';
import type { Department, Role, Settings, User } from '../types';

export function Admin() {
  const { api, user } = useSession();
  const savingUser = useIsMutating({ mutationKey: ['save-user'] }) > 0;
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.users() });
  const departments = useQuery({
    queryKey: ['departments'],
    queryFn: () => api.departments(),
  });
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings(),
  });
  const [editing, setEditing] = useState<User | 'new' | null>(null);
  const [message, setMessage] = useState('');
  const canEdit = !savingUser && !!departments.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ПОРЯДОК В ДЕТАЛЯХ</p>
          <h1>
            Люди и настройки<span className="heading-dot">.</span>
          </h1>
          <p className="muted">Всё, что нужно для общего обеда в офисе.</p>
        </div>
      </div>
      <div className="admin-layout">
        <div>
          <section className="panel" aria-labelledby="team-title">
            <div className="section-heading">
              <div>
                <h2 id="team-title">Команда</h2>
                {users.data && (
                  <p className="muted">{users.data.length} пользователей</p>
                )}
              </div>
              <button
                className="primary"
                disabled={!canEdit || !users.data}
                onClick={() => {
                  setEditing('new');
                  setMessage('');
                }}
              >
                + Сотрудник
              </button>
            </div>
            <LoadError
              error={users.error}
              label="пользователей"
              retry={() => users.refetch()}
              pending={users.isFetching}
            />
            <p className="success-message" role="status">
              {message}
            </p>
            {editing && departments.data && (
              <UserForm
                key={editing === 'new' ? 'new' : editing.id}
                editing={editing === 'new' ? undefined : editing}
                departments={departments.data}
                onClose={() => setEditing(null)}
                onSaved={() => {
                  setEditing(null);
                  setMessage('Сотрудник сохранён.');
                }}
                selfId={user.id}
              />
            )}
            {users.isPending ? (
              <Loading />
            ) : users.data?.length === 0 ? (
              <Empty>Сотрудников пока нет. Добавьте первого сотрудника.</Empty>
            ) : (
              users.data && (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Сотрудник</th>
                        <th>Роль / отдел</th>
                        <th>Лимит в день</th>
                        <th>Статус</th>
                        <th>
                          <span className="sr-only">Действия</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.data.map((u) => (
                        <tr key={u.id}>
                          <td>
                            <b>{u.full_name}</b>
                            <small>{u.email}</small>
                          </td>
                          <td>
                            {roles[u.role]}
                            <small>{u.department?.name ?? 'Без отдела'}</small>
                          </td>
                          <td>
                            {u.daily_limit_kopecks === null
                              ? 'Общий'
                              : money(u.daily_limit_kopecks)}
                          </td>
                          <td>
                            <span
                              className={`badge ${u.is_active === false ? 'inactive' : ''}`}
                            >
                              {u.is_active === undefined
                                ? 'Не указан'
                                : u.is_active
                                  ? 'Активен'
                                  : 'Отключён'}
                            </span>
                          </td>
                          <td>
                            <button
                              className="quiet"
                              aria-label={`Изменить ${u.full_name}`}
                              disabled={!canEdit}
                              onClick={() => {
                                setEditing(u);
                                setMessage('');
                              }}
                            >
                              Изменить
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}
          </section>
          {departments.data ? (
            <Departments departments={departments.data} />
          ) : (
            <section className="panel" aria-label="Отделы">
              <h2>Отделы</h2>
              {departments.isPending && <Loading />}
              <LoadError
                error={departments.error}
                label="отделов"
                retry={() => departments.refetch()}
                pending={departments.isFetching}
              />
            </section>
          )}
        </div>
        {settings.data ? (
          <SettingsForm settings={settings.data} />
        ) : (
          <aside className="panel settings" aria-label="Настройки">
            <p className="eyebrow">ПРАВИЛА ОФИСА</p>
            <h2>Настройки</h2>
            {settings.isPending && <Loading />}
            <LoadError
              error={settings.error}
              label="настроек"
              retry={() => settings.refetch()}
              pending={settings.isFetching}
            />
          </aside>
        )}
      </div>
    </>
  );
}
function LoadError({
  error,
  label,
  retry,
  pending,
}: {
  error: Error | null;
  label: string;
  retry: () => Promise<unknown>;
  pending: boolean;
}) {
  return error ? (
    <div>
      <ErrorNotice error={error} />
      <button type="button" disabled={pending} onClick={() => void retry()}>
        Повторить загрузку {label}
      </button>
    </div>
  ) : null;
}
function UserForm({
  editing,
  departments,
  onClose,
  onSaved,
  selfId,
}: {
  editing?: User;
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
  selfId: number;
}) {
  const { api } = useSession();
  const [email, setEmail] = useState(editing?.email ?? '');
  const [name, setName] = useState(editing?.full_name ?? '');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role>(editing?.role ?? 'employee');
  const [department, setDepartment] = useState(
    editing?.department?.id.toString() ?? '',
  );
  const [limit, setLimit] = useState(
    editing?.daily_limit_kopecks == null
      ? ''
      : String(editing.daily_limit_kopecks / 100),
  );
  const [active, setActive] = useState(editing ? editing.is_active : true);
  const action = useAction(async () => {
    await api.saveUser(
      {
        email: email.trim(),
        full_name: name.trim(),
        password,
        role,
        department_id: department ? Number(department) : null,
        daily_limit_kopecks: rublesToKopecks(limit),
        ...(active === undefined ? {} : { is_active: active }),
      },
      editing?.id,
    );
    onSaved();
  }, ['save-user', editing?.id]);
  return (
    <form
      className="inline-form"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate(undefined);
      }}
    >
      <h3>{editing ? 'Редактировать сотрудника' : 'Новый сотрудник'}</h3>
      <fieldset className="form-grid" disabled={action.isPending}>
        <label>
          Имя и фамилия
          <input
            required
            maxLength={255}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Почта
          <input
            type="email"
            required
            maxLength={320}
            disabled={!!editing}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        {editing?.id !== selfId && (
          <label>
            {editing ? 'Новый пароль (необязательно)' : 'Временный пароль'}
            <input
              type="password"
              autoComplete="new-password"
              required={!editing}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
        )}
        <label>
          Роль
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            {Object.entries(roles).map(([value, title]) => (
              <option key={value} value={value}>
                {title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Отдел
          <select
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          >
            <option value="">Без отдела</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Лимит ₽ / день
          <input
            inputMode="decimal"
            placeholder="Общий лимит"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
        {active === undefined ? (
          <label>
            Статус учётной записи
            <select
              value=""
              onChange={(e) => setActive(e.target.value === 'true')}
            >
              <option value="" disabled>
                Не указан — оставить без изменения
              </option>
              <option value="true">Активен</option>
              <option value="false">Отключён</option>
            </select>
          </label>
        ) : (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            Учётная запись активна
          </label>
        )}
      </fieldset>
      <ErrorNotice error={action.error} />
      <div className="form-actions">
        <button className="primary" disabled={action.isPending || !name.trim()}>
          {action.isPending ? 'Сохраняем…' : 'Сохранить сотрудника'}
        </button>
        <button type="button" disabled={action.isPending} onClick={onClose}>
          Отмена
        </button>
      </div>
    </form>
  );
}
function Departments({ departments }: { departments: Department[] }) {
  const { api } = useSession();
  const [id, setId] = useState<number | undefined>();
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const action = useAction(async () => {
    await api.saveDepartment(name.trim(), id);
    setName('');
    setId(undefined);
    setMessage('Отдел сохранён.');
  });
  return (
    <section className="panel">
      <h2>Отделы</h2>
      {departments.length === 0 && <p className="muted">Отделов пока нет.</p>}
      <div className="department-list">
        {departments.map((d) => (
          <button
            key={d.id}
            disabled={action.isPending}
            onClick={() => {
              setId(d.id);
              setName(d.name);
              setMessage('');
            }}
          >
            {d.name} <span aria-hidden="true">↗</span>
            <span className="sr-only"> — изменить отдел</span>
          </button>
        ))}
      </div>
      <form
        className="department-form"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate(undefined);
        }}
      >
        <label>
          {id === undefined ? 'Новый отдел' : 'Название отдела'}
          <input
            required
            maxLength={255}
            disabled={action.isPending}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Например, Маркетинг"
          />
        </label>
        <button disabled={action.isPending || !name.trim()}>
          {id === undefined ? 'Добавить отдел' : 'Сохранить отдел'}
        </button>
        {id !== undefined && (
          <button
            type="button"
            disabled={action.isPending}
            onClick={() => {
              setId(undefined);
              setName('');
            }}
          >
            Отмена
          </button>
        )}
      </form>
      <ErrorNotice error={action.error} />
      <small className="success-message" role="status">
        {message}
      </small>
    </section>
  );
}
function SettingsForm({ settings }: { settings: Settings }) {
  const { api } = useSession();
  const [cutoff, setCutoff] = useState(settings.cutoff_time);
  const [city, setCity] = useState(settings.mealty_city);
  const [limit, setLimit] = useState(
    settings.daily_limit_kopecks === null
      ? ''
      : String(settings.daily_limit_kopecks / 100),
  );
  const [quota, setQuota] = useState(settings.catalog_sync_per_day);
  const [saved, setSaved] = useState(false);
  const action = useAction(async () => {
    await api.saveSettings({
      cutoff_time: cutoff,
      mealty_city: city.trim(),
      timezone: settings.timezone,
      daily_limit_kopecks: rublesToKopecks(limit),
      catalog_sync_per_day: quota,
    });
    setSaved(true);
  });
  return (
    <aside className="panel settings">
      <p className="eyebrow">ПРАВИЛА ОФИСА</p>
      <h2>Настройки</h2>
      <form
        onChange={() => setSaved(false)}
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate(undefined);
        }}
      >
        <fieldset className="settings-fields" disabled={action.isPending}>
          <label>
            Закрытие приёма
            <input
              type="time"
              required
              value={cutoff}
              onChange={(e) => setCutoff(e.target.value)}
            />
          </label>
          <p className="muted">
            Накануне дня доставки, по московскому времени ({settings.timezone}).
          </p>
          <label>
            Город Mealty
            <input
              required
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </label>
          <label>
            Общий лимит ₽ / день
            <input
              inputMode="decimal"
              placeholder="Без лимита"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
          </label>
          <p className="muted">
            Оставьте пустым, чтобы отключить. Личный лимит сотрудника имеет
            приоритет.
          </p>
          <label>
            Обновлений каталога в сутки
            <input
              type="number"
              min="0"
              max="100"
              step="1"
              required
              value={quota}
              onChange={(e) => setQuota(Number(e.target.value))}
            />
          </label>
          <ErrorNotice error={action.error} />
          <button
            className="primary full"
            disabled={action.isPending || !city.trim()}
          >
            {action.isPending ? 'Сохраняем…' : 'Сохранить настройки'}
          </button>
          <p className="success-message" role="status">
            {saved ? '✓ Настройки сохранены' : ''}
          </p>
        </fieldset>
      </form>
    </aside>
  );
}
