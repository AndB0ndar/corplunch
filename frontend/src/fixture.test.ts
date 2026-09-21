// @vitest-environment node
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { expect, it } from 'vitest';
it('keeps three genuine cards, category wrappers, price attributes and lazy image paths offline', () => {
  const html = readFileSync(
    '../backend/tests/fixtures/mealty_catalog_qa.html',
    'utf8',
  );
  const expected = JSON.parse(
    readFileSync(
      '../backend/tests/fixtures/mealty_catalog.expected.json',
      'utf8',
    ),
  ) as {
    external_id: string;
    name: string;
    category: string;
    price_kopecks: number;
    image_path: string;
  }[];
  const doc = new JSDOM(html).window.document;
  expect(doc.querySelectorAll('.catalog-item')).toHaveLength(3);
  expect(doc.querySelectorAll('script, form, iframe')).toHaveLength(0);
  for (const row of expected) {
    const card = doc.querySelector(
      `[id="${row.category}"] .catalog-item[data-product_id="${row.external_id}"]`,
    )!;
    expect(card).toBeTruthy();
    expect(card.querySelector('.meal-card__name')?.textContent?.trim()).toBe(
      row.name,
    );
    expect(
      Number(card.querySelector('[data-price]')?.getAttribute('data-price')) *
        100,
    ).toBe(row.price_kopecks);
    expect(card.querySelector('img[data-src]')?.getAttribute('data-src')).toBe(
      row.image_path,
    );
  }
});
