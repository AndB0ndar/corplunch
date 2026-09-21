import { strToU8, zipSync } from 'fflate';
import type { Order } from './types';
const xml = (value: string | number) =>
  String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
const safeText = (value: string | number) =>
  typeof value === 'string' && /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
export function exportDemo(order: Order, format: 'csv' | 'xlsx'): Blob {
  const rows: (string | number)[][] = [
    ['external_id', 'name', 'qty', 'unit_price_kopecks', 'line_total_kopecks'],
    ...order.items.map((i) => [
      i.external_id,
      i.name,
      i.qty,
      i.unit_price_kopecks,
      i.line_total_kopecks,
    ]),
  ];
  if (format === 'csv')
    return new Blob(
      [
        '\uFEFF' +
          rows
            .map((r) =>
              r
                .map((v) => `"${String(safeText(v)).replaceAll('"', '""')}"`)
                .join(','),
            )
            .join('\r\n'),
      ],
      { type: 'text/csv;charset=utf-8' },
    );
  const employeeRows = [
    ['Сотрудник', 'Отдел', 'Сумма, коп.', 'Недоступных позиций'],
    ...order.by_employee.map((u) => [
      u.full_name,
      u.department_name ?? '',
      u.actual_total_kopecks,
      u.unavailable_count,
    ]),
  ];
  const worksheet = (data: (string | number)[][]) =>
    strToU8(
      `<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${data.map((r, n) => `<row r="${n + 1}">${r.map((v, c) => `<c r="${String.fromCharCode(65 + c)}${n + 1}" ${typeof v === 'number' ? '' : 't="inlineStr"'}>${typeof v === 'number' ? `<v>${v}</v>` : `<is><t>${xml(v)}</t></is>`}</c>`).join('')}</row>`).join('')}</sheetData></worksheet>`,
    );
  const files = {
    '[Content_Types].xml': strToU8(
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    ),
    '_rels/.rels': strToU8(
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    ),
    'xl/workbook.xml': strToU8(
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Заказ" sheetId="1" r:id="rId1"/><sheet name="По сотрудникам" sheetId="2" r:id="rId2"/></sheets></workbook>',
    ),
    'xl/_rels/workbook.xml.rels': strToU8(
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>',
    ),
    'xl/worksheets/sheet1.xml': worksheet(rows),
    'xl/worksheets/sheet2.xml': worksheet(employeeRows),
  };
  return new Blob([new Uint8Array(zipSync(files))], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}
