export const money = (kopecks: number) =>
  new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: kopecks % 100 ? 2 : 0,
  }).format(kopecks / 100);
export const roles = {
  employee: 'Сотрудник',
  procurement: 'Закупки',
  admin: 'Администратор',
};
export const categories: Record<string, string> = {
  breakfast: 'Завтраки',
  salad: 'Салаты',
  soup: 'Супы',
  main_dish: 'Вторые блюда',
  sandwich: 'Сэндвичи',
  dessert: 'Десерты',
  bread: 'Выпечка',
  drink: 'Напитки',
  snack: 'Снеки',
  novelty: 'Новинки',
};
export function today() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}
export function shiftDate(date: string, days: number) {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}
export function dateLabel(date: string, weekday = false) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    ...(weekday ? ({ weekday: 'long' } as const) : {}),
  }).format(new Date(`${date}T12:00:00Z`));
}
export function rublesToKopecks(value: string): number | null {
  if (!value.trim()) return null;
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(value.trim()))
    throw new Error('Введите сумму с точностью до копейки.');
  const [rubles, cents = ''] = value.trim().replace(',', '.').split('.');
  const result = Number(rubles) * 100 + Number(cents.padEnd(2, '0'));
  if (!Number.isSafeInteger(result)) throw new Error('Слишком большая сумма.');
  return result;
}
export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
