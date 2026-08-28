import assert from 'node:assert/strict';
import test from 'node:test';

import { watchJob } from './useJobPoll.js';

test('watchJob returns the terminal SSE result without polling', async () => {
  let pollingCalls = 0;
  const result = await watchJob(
    async () => {
      pollingCalls += 1;
      return { status: 'completed' };
    },
    'job-1',
    {
      streamStatus: async (_jobId, { onUpdate }) => {
        const status = { status: 'completed', progress: { stage: 'completed' } };
        onUpdate?.(status);
        return status;
      },
    },
  );

  assert.equal(result.status, 'completed');
  assert.equal(pollingCalls, 0);
});

test('watchJob falls back to polling when the SSE connection fails', async () => {
  let fallbackCalls = 0;
  const result = await watchJob(
    async () => ({ status: 'completed' }),
    'job-2',
    {
      streamStatus: async () => {
        throw new Error('connection lost');
      },
      onStreamFallback: () => {
        fallbackCalls += 1;
      },
      intervalMs: 1,
      jitterRatio: 0,
    },
  );

  assert.equal(result.status, 'completed');
  assert.equal(fallbackCalls, 1);
});
