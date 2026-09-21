import type { ReactNode } from 'react';
import { dateLabel, money, shiftDate } from './format';

export function ErrorNotice({ error }: { error: Error | null }) {
  return error ? (
    <div role="alert" className="notice error">
      {error.message}
    </div>
  ) : null;
}
export function Loading() {
  return (
    <div className="empty" role="status">
      <span className="spinner" /> Загружаем данные…
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function DatePicker({
  date,
  onChange,
  disabled = false,
}: {
  date: string;
  onChange: (date: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="date-picker">
      <button
        className="icon-button"
        aria-label="Предыдущий день"
        disabled={disabled}
        onClick={() => onChange(shiftDate(date, -1))}
      >
        ←
      </button>
      <label>
        <span>{dateLabel(date, true)}</span>
        <input
          aria-label="Дата доставки"
          disabled={disabled}
          type="date"
          value={date}
          onChange={(e) => {
            if (e.target.value) onChange(e.target.value);
          }}
        />
      </label>
      <button
        className="icon-button"
        aria-label="Следующий день"
        disabled={disabled}
        onClick={() => onChange(shiftDate(date, 1))}
      >
        →
      </button>
    </div>
  );
}
export function Metrics({
  planned,
  actual,
  unavailable = 0,
  collecting = false,
}: {
  planned: number;
  actual: number;
  unavailable?: number;
  collecting?: boolean;
}) {
  return (
    <div className="metrics">
      <div>
        <span>Плановая сумма</span>
        <strong>{money(planned)}</strong>
      </div>
      <div>
        <span>
          {collecting ? 'Предварительная сумма' : 'Фактическая сумма'}
        </span>
        <strong>{money(actual)}</strong>
      </div>
      <div>
        <span>Разница с планом</span>
        <strong className={actual > planned ? 'ochre' : ''}>
          {collecting
            ? '—'
            : `${actual > planned ? '+' : ''}${money(actual - planned)}`}
        </strong>
      </div>
      <div>
        <span>Нет в меню</span>
        <strong>
          {unavailable} <small>поз.</small>
        </strong>
      </div>
    </div>
  );
}
export function FoodArt({ category, id }: { category: string; id: number }) {
  const base =
    category === 'soup'
      ? '#d69749'
      : category === 'salad'
        ? '#789467'
        : category === 'dessert'
          ? '#ab7654'
          : '#d3b485';
  return (
    <svg className="food-art" viewBox="0 0 320 190" aria-hidden="true">
      <ellipse
        cx="161"
        cy="110"
        rx="113"
        ry="65"
        fill="#324234"
        opacity=".08"
      />
      <ellipse cx="160" cy="99" rx="108" ry="72" fill="#fcfaf3" />
      <ellipse cx="160" cy="99" rx="88" ry="55" fill="#ebe6d8" />
      <ellipse cx="160" cy="99" rx="79" ry="47" fill={base} />
      {Array.from({ length: 9 }, (_, n) => (
        <ellipse
          key={n}
          cx={110 + (n % 3) * 44}
          cy={73 + Math.floor(n / 3) * 26}
          rx={16 + (id % 4)}
          ry="10"
          transform={`rotate(${n * 13} ${110 + (n % 3) * 44} ${73 + Math.floor(n / 3) * 26})`}
          fill={n % 3 === 0 ? '#657f49' : n % 2 === 0 ? '#e4c38a' : '#be8557'}
        />
      ))}
      <path
        d="M147 74q17-27 27-21q-1 20-27 21M152 80q-23-16-29-6q9 17 29 6"
        fill="#3f6844"
      />
      <path
        d="M253 45v92m-7-92v29m14-29v29"
        stroke="#b1b7a6"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <path
        d="M61 45v91m0-91q-20 35 0 38"
        fill="none"
        stroke="#b1b7a6"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}
