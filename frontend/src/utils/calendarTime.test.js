import test from 'node:test';
import assert from 'node:assert/strict';
import { calendarDateTimeInput } from './calendarTime.js';

test('editing a task preserves its local deadline, including date boundaries and DST', () => {
  const originalTimezone = process.env.TZ;
  try {
    process.env.TZ = 'Asia/Ho_Chi_Minh';
    assert.equal(calendarDateTimeInput('2026-10-03T02:00:00Z'), '2026-10-03T09:00');
    assert.equal(calendarDateTimeInput('2026-10-02T18:30:00Z'), '2026-10-03T01:30');
    assert.equal(new Date(calendarDateTimeInput('2026-10-03T02:00:00Z')).toISOString(), '2026-10-03T02:00:00.000Z');
    process.env.TZ = 'America/New_York';
    assert.equal(calendarDateTimeInput('2026-07-01T13:00:00Z'), '2026-07-01T09:00');
    assert.equal(calendarDateTimeInput('2026-01-01T14:00:00Z'), '2026-01-01T09:00');
    assert.equal(calendarDateTimeInput(null), '');
    assert.equal(calendarDateTimeInput('invalid'), '');
  } finally {
    if (originalTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = originalTimezone;
  }
});
