import { useAction } from '../useAction';
import { useState } from 'react';
import { useIsMutating, useQuery } from '@tanstack/react-query';
import { ErrorNotice, Loading } from '../components';
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
      <ErrorNotice error={users.error ?? departments.error ?? settings.error} />
      {users.isPending || departments.isPending || settings.isPending ? (
        <Loading />
      ) : (
        <div className="admin-layout">
          <div>
            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Команда</h2>
                  <p className="muted">
                    {users.data?.length ?? 0} пользователей
                  </p>
                </div>
                <button
                  className="primary"
                  disabled={savingUser}
                  onClick={() => setEditing('new')}
                >
                  + Сотрудник
                </button>
              </div>
              {editing && (
                <UserForm
                  key={editing === 'new' ? 'new' : editing.id}
                  editing={editing === 'new' ? undefined : editing}
                  departments={departments.data ?? []}
                  onClose={() => setEditing(null)}
                  selfId={user.id}
                />
              )}
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
                    {users.data?.map((u) => (
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
                            {u.is_active === false ? 'Отключён' : 'Активен'}
                          </span>
                        </td>
                        <td>
                          <button
                            className="quiet"
                            aria-label={`Изменить ${u.full_name}`}
                            disabled={savingUser}
                            onClick={() => setEditing(u)}
                          >
                            Изменить
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <Departments departments={departments.data ?? []} />
          </div>
          {settings.data && <SettingsForm settings={settings.data} />}
        </div>
      )}
    </>
  );
}
function UserForm({
  editing,
  departments,
  onClose,
  selfId,
}: {
  editing?: User;
  departments: Department[];
  onClose: () => void;
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
  const [active, setActive] = useState(editing?.is_active ?? true);
  const action = useAction(async () => {
    await api.saveUser(
      {
        email: email.trim(),
        full_name: name.trim(),
        password,
        role,
        department_id: department ? Number(department) : null,
        daily_limit_kopecks: rublesToKopecks(limit),
        is_active: active,
      },
      editing?.id,
    );
    onClose();
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
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Почта
          <input
            type="email"
            required
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
        <label className="checkbox">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          Учётная запись активна
        </label>
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
              min="1"
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
