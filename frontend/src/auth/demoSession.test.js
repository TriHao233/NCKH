import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { readDemoSession } from './demoSession.js';

const originalLocalStorage = globalThis.localStorage;

afterEach(() => {
  globalThis.localStorage = originalLocalStorage;
});

function setSession(exp) {
  const values = new Map();
  const payload = Buffer.from(JSON.stringify({ exp })).toString('base64url');
  values.set('qbank_demo_session', JSON.stringify({
    token: `demo.${payload}.signature`,
    user: { role: 'Admin' },
  }));
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
  };
  return values;
}

test('expired demo sessions are removed before API requests', () => {
  const values = setSession(Math.floor(Date.now() / 1000) - 1);
  assert.equal(readDemoSession(), null);
  assert.equal(values.has('qbank_demo_session'), false);
});

test('valid demo sessions remain available', () => {
  const values = setSession(Math.floor(Date.now() / 1000) + 3600);
  assert.equal(readDemoSession()?.user.role, 'Admin');
  assert.equal(values.has('qbank_demo_session'), true);
});
