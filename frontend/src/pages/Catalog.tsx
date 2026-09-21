import { useAction } from '../useAction';
import { useEffect, useState } from 'react';
import { useIsMutating, useQuery, useQueryClient } from '@tanstack/react-query';
import { categories, dateLabel, money, shiftDate, today } from '../format';
import {
  DatePicker,
  Empty,
  ErrorNotice,
  FoodArt,
  Loading,
} from '../components';
import { useSession } from '../session';
import type { Dish, Plan, PlanItem } from '../types';

export function Catalog() {
  const { api } = useSession();
  const [date, setDate] = useState(shiftDate(today(), 2));
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [dirty, setDirty] = useState(false);
  const [mobilePlan, setMobilePlan] = useState(false);
  const saving = useIsMutating({ mutationKey: ['save-plan'] }) > 0;
  const catalog = useQuery({
    queryKey: ['catalog'],
    queryFn: () => api.catalog(),
  });
  const plan = useQuery({
    queryKey: ['plan', date],
    queryFn: () => api.plan(date),
    refetchInterval: dirty ? false : 30000,
  });
  useEffect(() => {
    const leave = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    const logout = (event: Event) => {
      if (
        dirty &&
        !window.confirm('План не сохранён. Выйти и отменить изменения?')
      )
        event.preventDefault();
    };
    window.addEventListener('beforeunload', leave);
    window.addEventListener('corplunch:before-logout', logout);
    return () => {
      window.removeEventListener('beforeunload', leave);
      window.removeEventListener('corplunch:before-logout', logout);
    };
  }, [dirty]);
  const chooseDate = (next: string) => {
    if (saving || next === date) return;
    if (
      !dirty ||
      window.confirm(
        'В плане есть несохранённые изменения. Перейти на другую дату?',
      )
    ) {
      setDirty(false);
      setDate(next);
    }
  };
  const dishes = catalog.data ?? [];
  const visible = dishes.filter(
    (d) =>
      (category === 'all' || d.category === category) &&
      `${d.name} ${d.subtitle}`
        .toLocaleLowerCase('ru')
        .includes(search.toLocaleLowerCase('ru')),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ОБЕД, КОТОРОГО ЖДЁШЬ</p>
          <h1>
            Меню и ваш план<span className="heading-dot">.</span>
          </h1>
          <p className="muted">
            Выбирайте сегодня — наслаждайтесь в день доставки.
          </p>
        </div>
        <DatePicker date={date} onChange={chooseDate} disabled={saving} />
      </div>
      <div className="mobile-tabs">
        <button aria-pressed={!mobilePlan} onClick={() => setMobilePlan(false)}>
          Каталог
        </button>
        <button aria-pressed={mobilePlan} onClick={() => setMobilePlan(true)}>
          Мой план {dirty ? '•' : ''}
        </button>
      </div>
      <ErrorNotice error={catalog.error ?? plan.error} />
      {catalog.isPending || plan.isPending ? (
        <Loading />
      ) : (
        plan.data && (
          <PlanEditor
            key={date}
            plan={plan.data}
            dishes={dishes}
            date={date}
            dirty={dirty}
            onDirty={setDirty}
            mobilePlan={mobilePlan}
          >
            <div className="catalog-tools">
              <label className="search">
                <span>⌕</span>
                <input
                  aria-label="Поиск блюд"
                  placeholder="Найти что-нибудь вкусное"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <small>{visible.length} блюд</small>
            </div>
            <div className="chips">
              <button
                className={category === 'all' ? 'selected' : ''}
                onClick={() => setCategory('all')}
              >
                Всё меню
              </button>
              {Object.entries(categories)
                .filter(([id]) => dishes.some((d) => d.category === id))
                .map(([id, label]) => (
                  <button
                    className={category === id ? 'selected' : ''}
                    key={id}
                    onClick={() => setCategory(id)}
                  >
                    {label}
                  </button>
                ))}
            </div>
            <CatalogCards dishes={visible} />
          </PlanEditor>
        )
      )}
    </>
  );
}
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
const EditorContext = createContext<{
  add: (dish: Dish) => void;
  editable: boolean;
  items: PlanItem[];
} | null>(null);
function CatalogCards({ dishes }: { dishes: Dish[] }) {
  const editor = useContext(EditorContext)!;
  return dishes.length ? (
    <div className="dish-grid">
      {dishes.map((dish) => (
        <article
          className={`dish-card ${!dish.available ? 'unavailable' : ''}`}
          key={dish.id}
        >
          <div className={`dish-picture tone-${dish.id % 4}`}>
            {dish.image_url ? (
              <img
                src={dish.image_url}
                alt={dish.name}
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            ) : (
              <FoodArt category={dish.category} id={dish.id} />
            )}
            <span className="dish-category">
              {categories[dish.category] ?? dish.category}
            </span>
          </div>
          <div className="dish-body">
            <h2>{dish.name}</h2>
            <p>{dish.subtitle}</p>
            <div className="nutrition">
              {dish.weight_g !== null && <span>{dish.weight_g} г</span>}
              {dish.calories !== null && <span>{dish.calories} ккал</span>}
            </div>
            <details className="dish-detail">
              <summary>Состав и КБЖУ</summary>
              <p>{dish.description ?? 'Описание не указано.'}</p>
              <p>
                Б {dish.proteins ?? '—'} · Ж {dish.fats ?? '—'} · У{' '}
                {dish.carbs ?? '—'}
              </p>
            </details>
            <div className="dish-bottom">
              <div>
                <strong>{money(dish.price_kopecks)}</strong>
                {dish.old_price_kopecks !== null && (
                  <del>{money(dish.old_price_kopecks)}</del>
                )}
              </div>
              <button
                aria-label={`Добавить ${dish.name}`}
                className="add-button"
                disabled={!editor.editable || !dish.available}
                onClick={() => editor.add(dish)}
              >
                +
                <span>
                  {editor.items.find((i) => i.dish_id === dish.id)?.qty ||
                    'В план'}
                </span>
              </button>
            </div>
            {!dish.available && (
              <small className="terracotta">Нет в меню Mealty</small>
            )}
          </div>
        </article>
      ))}
    </div>
  ) : (
    <Empty>Ничего не нашлось. Попробуйте другую категорию или название.</Empty>
  );
}
function PlanEditor({
  plan,
  dishes,
  date,
  dirty,
  onDirty,
  mobilePlan,
  children,
}: {
  plan: Plan;
  dishes: Dish[];
  date: string;
  dirty: boolean;
  onDirty: (value: boolean) => void;
  mobilePlan: boolean;
  children: ReactNode;
}) {
  const { api, user } = useSession();
  const client = useQueryClient();
  const [draft, setDraft] = useState<PlanItem[] | null>(null);
  const [saved, setSaved] = useState(false);
  const editable = plan.editable;
  // Once the server locks the day, only its saved composition is authoritative.
  const items = editable ? (draft ?? plan.items) : plan.items;
  useEffect(() => {
    if (!editable) {
      setDraft(null);
      onDirty(false);
    }
  }, [editable, onDirty]);
  const total = items.reduce(
    (sum, item) =>
      sum +
      item.qty *
        (plan.status === 'draft'
          ? (dishes.find((d) => d.id === item.dish_id)?.price_kopecks ??
            item.planned_price_kopecks)
          : item.planned_price_kopecks),
    0,
  );
  const overLimit =
    user.daily_limit_kopecks !== null && total > user.daily_limit_kopecks;
  const save = useAction(async () => {
    await api.savePlan(
      date,
      items.map(({ dish_id, qty }) => ({ dish_id, qty })),
    );
    await client.invalidateQueries({ queryKey: ['plan', date] });
    setDraft(null);
    onDirty(false);
    setSaved(true);
  }, ['save-plan', user.id, date]);
  function change(next: PlanItem[]) {
    if (!editable) return;
    setDraft(next);
    onDirty(true);
    setSaved(false);
    save.reset();
  }
  function add(d: Dish) {
    const existing = items.find((i) => i.dish_id === d.id);
    change(
      existing
        ? items.map((i) => (i.dish_id === d.id ? { ...i, qty: i.qty + 1 } : i))
        : [
            ...items,
            {
              dish_id: d.id,
              name: d.name,
              qty: 1,
              planned_price_kopecks: d.price_kopecks,
              actual_price_kopecks: null,
              unavailable: false,
            },
          ],
    );
  }
  return (
    <EditorContext.Provider
      value={{ add, editable: editable && !save.isPending, items }}
    >
      <div className={`catalog-layout ${mobilePlan ? 'show-plan' : ''}`}>
        <section className="catalog-section">
          {!editable && (
            <div className="notice">
              Приём заказов на эту дату закрыт. Изменить состав уже нельзя.
            </div>
          )}
          {children}
        </section>
        <aside className="plan-panel">
          <div className="plan-title">
            <span className="eyebrow">ВАШ ОБЕД</span>
            <span className="badge">
              {editable ? 'Приём открыт' : 'Приём закрыт'}
            </span>
          </div>
          <h2>План на {dateLabel(date)}</h2>
          <p className="muted">
            {editable
              ? 'Сохраните состав, когда всё выберете.'
              : 'Состав зафиксирован для закупки.'}
          </p>
          {items.length ? (
            <ul className="plan-list">
              {items.map((item) => (
                <li key={item.dish_id}>
                  <div>
                    <b>{item.name}</b>
                    <span>
                      {item.unavailable ? (
                        <span className="terracotta">Нет в меню Mealty</span>
                      ) : (
                        money(
                          (plan.status === 'draft'
                            ? (dishes.find((d) => d.id === item.dish_id)
                                ?.price_kopecks ?? item.planned_price_kopecks)
                            : (item.actual_price_kopecks ??
                              item.planned_price_kopecks)) * item.qty,
                        )
                      )}
                    </span>
                    {item.actual_price_kopecks !== null &&
                      item.actual_price_kopecks !==
                        item.planned_price_kopecks && (
                        <small className="ochre">
                          Цена изменилась: {money(item.planned_price_kopecks)} →{' '}
                          {money(item.actual_price_kopecks)}
                        </small>
                      )}
                  </div>
                  <div className="quantity">
                    <button
                      aria-label={`Уменьшить ${item.name}`}
                      disabled={!editable || save.isPending}
                      onClick={() =>
                        change(
                          items.flatMap((i) =>
                            i.dish_id !== item.dish_id
                              ? [i]
                              : i.qty > 1
                                ? [{ ...i, qty: i.qty - 1 }]
                                : [],
                          ),
                        )
                      }
                    >
                      −
                    </button>
                    <span>{item.qty}</span>
                    <button
                      aria-label={`Увеличить ${item.name}`}
                      disabled={
                        !editable ||
                        save.isPending ||
                        item.unavailable ||
                        !dishes.find((d) => d.id === item.dish_id)?.available
                      }
                      onClick={() =>
                        change(
                          items.map((i) =>
                            i.dish_id === item.dish_id
                              ? { ...i, qty: i.qty + 1 }
                              : i,
                          ),
                        )
                      }
                    >
                      +
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>
              <span className="empty-mark">↗</span>Здесь будет ваш обед.
              <br />
              Добавьте блюда из меню.
            </Empty>
          )}
          <div className="plan-total">
            <span>{editable ? 'Ориентировочно' : 'Плановая сумма'}</span>
            <strong>{money(total)}</strong>
          </div>
          {!editable && (
            <div className="plan-total">
              <span>К закупке</span>
              <strong>
                {plan.actual_total_kopecks === null
                  ? 'Уточняется'
                  : money(plan.actual_total_kopecks)}
              </strong>
            </div>
          )}
          {user.daily_limit_kopecks !== null && (
            <p className={overLimit ? 'terracotta' : 'muted'}>
              Дневной лимит: {money(user.daily_limit_kopecks)}
            </p>
          )}
          <ErrorNotice error={save.error} />
          {editable && (
            <button
              className="primary full"
              disabled={save.isPending || overLimit || !dirty}
              onClick={() => save.mutate(undefined)}
            >
              {save.isPending ? 'Сохраняем…' : 'Сохранить план'}
            </button>
          )}
          <p className="save-status" role="status">
            {saved
              ? '✓ План сохранён'
              : dirty
                ? 'Есть несохранённые изменения'
                : ''}
          </p>
          <p className="plan-note">
            Цены и наличие уточняются при закрытии приёма. Время офиса — Москва.
          </p>
        </aside>
      </div>
    </EditorContext.Provider>
  );
}
