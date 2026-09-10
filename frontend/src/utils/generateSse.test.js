import assert from 'node:assert/strict';
import test from 'node:test';

import { parseGenerateStatusSseFrame } from './generateSse.js';

test('parseGenerateStatusSseFrame parses valid status events', () => {
  const payload = parseGenerateStatusSseFrame(
    'event: status\ndata: {"status":"processing","progress":{"stage":"generating"}}',
  );

  assert.equal(payload.status, 'processing');
  assert.equal(payload.progress.stage, 'generating');
});

test('parseGenerateStatusSseFrame ignores heartbeat frames', () => {
  assert.equal(parseGenerateStatusSseFrame(': keep-alive'), null);
});

test('parseGenerateStatusSseFrame rejects payloads without status', () => {
  assert.throws(
    () => parseGenerateStatusSseFrame('event: status\ndata: {"detail":"missing"}'),
    /không hợp lệ/,
  );
});

test('parseGenerateStatusSseFrame turns SSE error events into stream failures', () => {
  assert.throws(
    () => parseGenerateStatusSseFrame('event: error\ndata: {"detail":"Job không còn tồn tại"}'),
    /Job không còn tồn tại/,
  );
});
