import { describe, expect, it } from 'vitest';
import { beforeCutoff } from './demo';
import { rublesToKopecks, shiftDate } from './format';
describe('Money and office dates', () => {
  it('keeps exact kopecks and distinguishes no limit from zero', () => {
    expect(rublesToKopecks('410,05')).toBe(41005);
    expect(rublesToKopecks('0')).toBe(0);
    expect(rublesToKopecks('')).toBeNull();
    expect(() => rublesToKopecks('1.005')).toThrow();
    expect(() => rublesToKopecks('-10')).toThrow();
  });
  it('handles month and year boundaries', () => {
    expect(shiftDate('2027-01-01', -1)).toBe('2026-12-31');
  });
  it('locks at exactly 16:00 Moscow on the previous day', () => {
    expect(
      beforeCutoff('2026-09-20', '16:00', Date.parse('2026-09-19T12:59:59Z')),
    ).toBe(true);
    expect(
      beforeCutoff('2026-09-20', '16:00', Date.parse('2026-09-19T13:00:00Z')),
    ).toBe(false);
  });
});
