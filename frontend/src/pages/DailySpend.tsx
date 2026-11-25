import { useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { ErrorNotice, Loading } from '../components';
import { money, shiftDate } from '../format';
import { useSession } from '../session';

export function DailySpend({
  from,
  to,
  department,
  total,
}: {
  from: string;
  to: string;
  department: string;
  total: number;
}) {
  const { api } = useSession();
  const [start, setStart] = useState(from);
  const days = [start];
  while (days.length < 7 && days[days.length - 1] < to)
    days.push(shiftDate(days[days.length - 1], 1));
  const end = days[days.length - 1];
  const results = useQueries({
    queries: (from === to ? [] : days).map((day) => ({
      queryKey: department
        ? ['stats', day, day, department]
        : ['stats', day, day],
      queryFn: () =>
        api.stats({
          from: day,
          to: day,
          ...(department && { department_id: Number(department) }),
        }),
      staleTime: 30_000,
    })),
  });
  const values =
    from === to
      ? [total]
      : results.map((r) => r.data?.total_actual_kopecks ?? 0);
  const max = Math.max(1, ...values);
  const error = results.find((r) => r.error)?.error;
  return (
    <section className="panel" aria-label="Расходы по дням">
      <div className="section-heading">
        <h2>Расходы по дням</h2>
        {(start !== from || end !== to) && (
          <div>
            <button
              aria-label="Предыдущие дни"
              disabled={start === from}
              onClick={() => setStart(shiftDate(start, -7))}
            >
              ◀
            </button>
            <button
              aria-label="Следующие дни"
              disabled={end === to}
              onClick={() => setStart(shiftDate(end, 1))}
            >
              ▶
            </button>
          </div>
        )}
      </div>
      {error ? (
        <ErrorNotice error={error} />
      ) : results.some((r) => r.isPending) ? (
        <Loading />
      ) : (
        <ul className="daily-spend">
          {days.map((day, i) => (
            <li key={day}>
              <time dateTime={day}>{day.split('-').reverse().join('.')}</time>
              <span className="daily-bar" aria-hidden="true">
                <i style={{ width: (values[i] / max) * 100 + '%' }} />
              </span>
              <strong>{money(values[i])}</strong>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
