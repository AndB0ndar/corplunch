import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Empty, ErrorNotice, Loading, Metrics } from '../components';
import { money, shiftDate, today } from '../format';
import { useSession } from '../session';

export function Statistics() {
  const { api } = useSession();
  const [from, setFrom] = useState(shiftDate(today(), -7));
  const [to, setTo] = useState(shiftDate(today(), 7));
  const [department, setDepartment] = useState('');
  const valid = !!from && !!to && from <= to;
  const all = useQuery({
    queryKey: ['stats', from, to],
    queryFn: () => api.stats({ from, to }),
    enabled: valid,
  });
  const filtered = useQuery({
    queryKey: ['stats', from, to, department],
    queryFn: () => api.stats({ from, to, department_id: Number(department) }),
    enabled: valid && !!department,
  });
  const query = department ? filtered : all;
  const stats = query.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ОБЕДЫ В ЦИФРАХ</p>
          <h1>
            Статистика<span className="heading-dot">.</span>
          </h1>
          <p className="muted">
            Расходы офиса и разница между планом и фактом.
          </p>
        </div>
      </div>
      <div className="filters panel">
        <label>
          С
          <input
            type="date"
            value={from}
            onChange={(e) => {
              setFrom(e.target.value);
              setDepartment('');
            }}
          />
        </label>
        <label>
          По
          <input
            type="date"
            value={to}
            onChange={(e) => {
              setTo(e.target.value);
              setDepartment('');
            }}
          />
        </label>
        <label>
          Отдел
          <select
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          >
            <option value="">Все отделы</option>
            {all.data?.by_department.map((d) => (
              <option value={d.department_id} key={d.department_id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <span className="muted">По дате доставки · закрытые заказы</span>
      </div>
      {!valid ? (
        <div className="notice error" role="alert">
          Дата начала должна быть не позже даты окончания.
        </div>
      ) : (
        <>
          <ErrorNotice error={query.error} />
          {query.isPending ? (
            <Loading />
          ) : (
            stats && (
              <>
                <Metrics
                  planned={stats.total_planned_kopecks}
                  actual={stats.total_actual_kopecks}
                  unavailable={stats.unavailable_count}
                />
                {!stats.by_employee.length ? (
                  <Empty>
                    В этом периоде пока нет закрытых заказов. Выберите другой
                    период или закройте приём в сводке дня.
                  </Empty>
                ) : (
                  <>
                    <div className="stats-grid">
                      <section className="panel">
                        <div className="section-heading">
                          <h2>Расходы по отделам</h2>
                          <span className="muted">Фактические</span>
                        </div>
                        {stats.by_department.map((d) => (
                          <div className="bar-row" key={d.department_id}>
                            <div>
                              <span>{d.name}</span>
                              <b>{money(d.actual_kopecks)}</b>
                            </div>
                            <div className="bar-track">
                              <div
                                style={{
                                  width: `${stats.total_actual_kopecks ? (d.actual_kopecks / stats.total_actual_kopecks) * 100 : 0}%`,
                                }}
                              />
                            </div>
                            <small className="muted">
                              Планов сотрудников: {d.order_count}
                            </small>
                          </div>
                        ))}
                      </section>
                      <section className="panel">
                        <div className="section-heading">
                          <h2>Любимые блюда</h2>
                          <span className="muted">По количеству</span>
                        </div>
                        {stats.top_dishes.map((d, n) => (
                          <div className="ranking" key={d.dish_id}>
                            <span className="rank">
                              {String(n + 1).padStart(2, '0')}
                            </span>
                            <div>
                              <b>{d.name}</b>
                              <small>{money(d.actual_kopecks)}</small>
                            </div>
                            <strong>
                              {d.qty} <small>шт.</small>
                            </strong>
                          </div>
                        ))}
                      </section>
                    </div>
                    <section className="panel">
                      <h2>По сотрудникам</h2>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Сотрудник</th>
                              <th className="numeric">Планов</th>
                              <th className="numeric">Фактическая сумма</th>
                            </tr>
                          </thead>
                          <tbody>
                            {stats.by_employee.map((u) => (
                              <tr key={u.user_id}>
                                <td>{u.full_name}</td>
                                <td className="numeric">{u.order_count}</td>
                                <td className="numeric">
                                  {money(u.actual_kopecks)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>
                    {stats.price_changes.length > 0 && (
                      <section className="panel">
                        <h2>Изменения цен</h2>
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Блюдо</th>
                                <th className="numeric">План</th>
                                <th className="numeric">Факт</th>
                              </tr>
                            </thead>
                            <tbody>
                              {stats.price_changes.map((d, i) => (
                                <tr key={`${d.dish_id}-${i}`}>
                                  <td>{d.name}</td>
                                  <td className="numeric">
                                    {money(d.planned_price_kopecks)}
                                  </td>
                                  <td className="numeric ochre">
                                    {money(d.actual_price_kopecks)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    )}
                  </>
                )}
              </>
            )
          )}
        </>
      )}
    </>
  );
}
