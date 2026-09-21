import { useAction } from '../useAction';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  DatePicker,
  Empty,
  ErrorNotice,
  Loading,
  Metrics,
} from '../components';
import { download, money, shiftDate, today } from '../format';
import { useSession } from '../session';

const statuses = {
  collecting: 'Собираем планы',
  locked: 'Приём закрыт',
  exported: 'Список выгружен',
  placed: 'Заказ размещён',
};
export function Orders() {
  const { api, demo } = useSession();
  const [date, setDate] = useState(shiftDate(today(), 2));
  const [confirm, setConfirm] = useState<'cutoff' | 'place' | null>(null);
  const [message, setMessage] = useState('');
  const query = useQuery({
    queryKey: ['order', date],
    queryFn: () => api.order(date),
  });
  const action = useAction(
    async (kind: 'sync' | 'cutoff' | 'place' | 'csv' | 'xlsx') => {
      setMessage('');
      if (kind === 'sync') {
        await api.sync();
        setMessage('Каталог обновлён.');
      } else if (kind === 'cutoff') {
        await api.cutoff(date);
        setMessage('Приём закрыт. Цены и наличие уточнены.');
      } else if (kind === 'place') {
        await api.place(date);
        setMessage('Заказ отмечен как размещённый.');
      } else {
        download(
          await api.exportOrder(date, kind),
          `corplunch-${date}.${kind}`,
        );
        setMessage('Список для заказа скачан.');
      }
      setConfirm(null);
    },
  );
  const order = query.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ВСЁ ДЛЯ ОБЩЕГО ОБЕДА</p>
          <h1>
            Сводка дня<span className="heading-dot">.</span>
          </h1>
          <p className="muted">
            Один список для закупки. Каждый обед на своём месте.
          </p>
        </div>
        <DatePicker
          disabled={action.isPending}
          date={date}
          onChange={(d) => {
            setDate(d);
            setConfirm(null);
            action.reset();
            setMessage('');
          }}
        />
      </div>
      <ErrorNotice error={query.error ?? action.error} />
      <div role="status" className="success-message">
        {message}
      </div>
      {query.isPending ? (
        <Loading />
      ) : (
        order && (
          <>
            <div className="order-toolbar">
              <span className="badge">● {statuses[order.status]}</span>
              <button
                disabled={action.isPending}
                onClick={() => action.mutate('sync')}
              >
                ↻ Обновить каталог
              </button>
              {order.status === 'collecting' ? (
                <button
                  className="primary"
                  disabled={action.isPending || order.by_employee.length === 0}
                  onClick={() => setConfirm('cutoff')}
                >
                  Закрыть приём заказов
                </button>
              ) : (
                <>
                  <button
                    disabled={action.isPending}
                    onClick={() => action.mutate('csv')}
                  >
                    ↓ Скачать CSV
                  </button>
                  <button
                    disabled={action.isPending}
                    onClick={() => action.mutate('xlsx')}
                  >
                    ↓ Скачать Excel
                  </button>
                  <button
                    className="primary"
                    disabled={action.isPending || order.status === 'placed'}
                    onClick={() => setConfirm('place')}
                  >
                    {order.status === 'placed'
                      ? '✓ Заказ размещён'
                      : 'Заказ размещён'}
                  </button>
                </>
              )}
            </div>
            {confirm && (
              <div
                className="notice confirmation"
                role="region"
                aria-label="Подтверждение действия"
              >
                <div>
                  <b>
                    {confirm === 'cutoff'
                      ? 'Закрыть приём на выбранную дату?'
                      : 'Заказ уже оформлен на Mealty?'}
                  </b>
                  <p>
                    {confirm === 'cutoff'
                      ? 'Планы сотрудников станут недоступны для редактирования. Будут уточнены цены и наличие.'
                      : 'Эта отметка сохраняет факт ручного размещения. Она не отправляет заказ поставщику.'}
                  </p>
                </div>
                <button
                  className="primary"
                  disabled={action.isPending}
                  onClick={() => action.mutate(confirm)}
                >
                  {action.isPending ? 'Выполняем…' : 'Подтвердить'}
                </button>
                <button
                  disabled={action.isPending}
                  onClick={() => setConfirm(null)}
                >
                  Отмена
                </button>
              </div>
            )}
            <Metrics
              planned={order.totals.planned_kopecks}
              actual={order.totals.actual_kopecks}
              unavailable={order.totals.unavailable_count}
              collecting={order.status === 'collecting'}
            />
            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Список для заказа</h2>
                  <p className="muted">
                    {order.status === 'collecting'
                      ? 'Предварительный состав. Цены будут уточнены после закрытия приёма.'
                      : 'Только доступные блюда по зафиксированным ценам.'}
                  </p>
                </div>
                <span className="count">{order.items.length} позиций</span>
              </div>
              {order.items.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Блюдо</th>
                        <th>Артикул</th>
                        <th className="numeric">Кол-во</th>
                        <th className="numeric">Цена</th>
                        <th className="numeric">Сумма</th>
                      </tr>
                    </thead>
                    <tbody>
                      {order.items.map((i) => (
                        <tr key={i.dish_id}>
                          <td>
                            <b>{i.name}</b>
                          </td>
                          <td className="muted">{i.external_id}</td>
                          <td className="numeric">{i.qty}</td>
                          <td className="numeric">
                            {money(i.unit_price_kopecks)}
                          </td>
                          <td className="numeric">
                            <b>{money(i.line_total_kopecks)}</b>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty>
                  Пока нет блюд для закупки. Сотрудникам нужно сохранить планы
                  на эту дату.
                </Empty>
              )}
            </section>
            <section className="panel">
              <div className="section-heading">
                <h2>По сотрудникам</h2>
                <span className="count">
                  {order.by_employee.length} человек
                </span>
              </div>
              {order.by_employee.map((person) => (
                <details className="employee-row" key={person.user_id}>
                  <summary>
                    <span>
                      <b>{person.full_name}</b>
                      <small>
                        {person.department_name ?? 'Без отдела'}
                        {person.unavailable_count > 0
                          ? ` · нет в меню: ${person.unavailable_count}`
                          : ''}
                      </small>
                    </span>
                    <strong>
                      {money(person.actual_total_kopecks)}{' '}
                      <span className="muted">⌄</span>
                    </strong>
                  </summary>
                  <EmployeePlan date={date} userId={person.user_id} />
                </details>
              ))}
            </section>
            <p className="muted">
              Заказ на Mealty оформляется вручную.{' '}
              {demo &&
                'В демо при закрытии ньокки дорожают на 15 ₽, салат исчезает из меню.'}
            </p>
          </>
        )
      )}
    </>
  );
}
function EmployeePlan({ date, userId }: { date: string; userId: number }) {
  const { api } = useSession();
  const query = useQuery({
    queryKey: ['plan', date, userId],
    queryFn: () => api.plan(date, userId),
  });
  if (query.isPending) return <Loading />;
  return (
    <>
      <ErrorNotice error={query.error} />
      {query.data?.items.map((i) => (
        <div className="read-plan-row" key={i.dish_id}>
          <span>
            {i.name} × {i.qty}
          </span>
          <span>
            {i.unavailable
              ? 'Нет в меню Mealty'
              : money(
                  (i.actual_price_kopecks ?? i.planned_price_kopecks) * i.qty,
                )}
          </span>
        </div>
      ))}
    </>
  );
}
