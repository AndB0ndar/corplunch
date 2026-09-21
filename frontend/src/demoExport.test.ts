// @vitest-environment node
import { expect, it } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import { exportDemo } from './demoExport';
import type { Order } from './types';
const order: Order = {
  delivery_date: '2026-09-20',
  status: 'locked',
  totals: {
    planned_kopecks: 41000,
    actual_kopecks: 42500,
    delta_kopecks: 1500,
    unavailable_count: 0,
  },
  items: [
    {
      dish_id: 1,
      external_id: '875',
      name: '=HYPERLINK("x")',
      qty: 1,
      unit_price_kopecks: 42500,
      line_total_kopecks: 42500,
    },
  ],
  by_employee: [
    {
      user_id: 1,
      full_name: 'Анна & Иван',
      department_id: 1,
      department_name: 'QA',
      actual_total_kopecks: 42500,
      unavailable_count: 0,
    },
  ],
};
it('exports CSV with kopecks, quoting and protection against spreadsheet formulas', async () => {
  const text = await exportDemo(order, 'csv').text();
  expect(text).toContain('unit_price_kopecks');
  expect(text).toContain('42500');
  expect(text).toContain("'=HYPERLINK");
});
it('creates an actual XLSX zip with an employee sheet and numeric kopecks', async () => {
  const blob = exportDemo(order, 'xlsx');
  const files = unzipSync(new Uint8Array(await blob.arrayBuffer()));
  expect(strFromU8(files['xl/workbook.xml'])).toContain('По сотрудникам');
  expect(strFromU8(files['xl/worksheets/sheet1.xml'])).toContain(
    '<v>42500</v>',
  );
  expect(strFromU8(files['xl/worksheets/sheet2.xml'])).toContain(
    'Анна &amp; Иван',
  );
});
