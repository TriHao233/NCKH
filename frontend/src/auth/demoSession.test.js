import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  SESSION_EXPIRED_EVENT,
  expireDemoSession,
  handleDemoSessionResponse,
  readDemoSession,
  saveDemoSession,
} from './demoSession.js';

function demoToken(name, expiresInSeconds = 3600) {
  const exp = Math.floor(Date.now() / 1000) + expiresInSeconds;
  const payload = Buffer.from(JSON.stringify({ exp, sub: name })).toString('base64url');
  return `demo.${payload}.signature`;
}

function withBrowserGlobals(run) {
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const previousDispatch = Object.getOwnPropertyDescriptor(globalThis, 'dispatchEvent');
  const values = new Map();
  const events = new EventTarget();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  } });
  Object.defineProperty(globalThis, 'dispatchEvent', {
    configurable: true,
    value: (event) => events.dispatchEvent(event),
  });
  try {
    run({ values, events });
  } finally {
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage);
    else delete globalThis.localStorage;
    if (previousDispatch) Object.defineProperty(globalThis, 'dispatchEvent', previousDispatch);
    else delete globalThis.dispatchEvent;
  }
}

test('expired demo sessions are removed before API requests', () => withBrowserGlobals(({ values }) => {
  saveDemoSession(demoToken('admin', -1), { role: 'Admin' });
  assert.equal(readDemoSession(), null);
  assert.equal(values.has('qbank_demo_session'), false);
}));

test('valid demo sessions remain available', () => withBrowserGlobals(({ values }) => {
  saveDemoSession(demoToken('admin'), { role: 'Admin' });
  assert.equal(readDemoSession()?.user.role, 'Admin');
  assert.equal(values.has('qbank_demo_session'), true);
}));

test('malformed demo tokens are treated as no session', () => withBrowserGlobals(({ values }) => {
  saveDemoSession('demo.not-base64-json', { role: 'Admin' });
  assert.equal(readDemoSession(), null);
  assert.equal(values.has('qbank_demo_session'), false);
}));

test('a rejected current demo session clears cached user and sends one expiry event', () => withBrowserGlobals(({ values, events }) => {
  const token = demoToken('reviewer');
  saveDemoSession(token, { role: 'Reviewer' });
  values.set('userInfo', '{}');
  let count = 0;
  events.addEventListener(SESSION_EXPIRED_EVENT, () => { count += 1; });
  assert.equal(handleDemoSessionResponse(401, `Bearer ${token}`), true);
  assert.equal(readDemoSession(), null);
  assert.equal(values.has('userInfo'), false);
  assert.equal(handleDemoSessionResponse(401, `Bearer ${token}`), false);
  assert.equal(count, 1);
}));

test('a late response for an old session cannot clear the new login', () => withBrowserGlobals(({ values }) => {
  const current = demoToken('new-login');
  saveDemoSession(current, { role: 'Admin' });
  values.set('userInfo', 'new-user');
  assert.equal(handleDemoSessionResponse(401, `Bearer ${demoToken('old-login')}`), false);
  assert.equal(readDemoSession().token, current);
  assert.equal(values.get('userInfo'), 'new-user');
}));

test('permission errors, server errors and Firebase failures leave demo state alone', () => withBrowserGlobals(() => {
  const token = demoToken('reviewer');
  saveDemoSession(token, { role: 'Reviewer' });
  for (const status of [200, 403, 409, 500, 503]) {
    assert.equal(handleDemoSessionResponse(status, `Bearer ${token}`), false);
  }
  assert.equal(handleDemoSessionResponse(401, 'Bearer firebase-token'), false);
  assert.equal(handleDemoSessionResponse(401, undefined), false);
  assert.equal(readDemoSession().token, token);
}));

test('expiry without a matching session does not clear an unrelated cached user', () => withBrowserGlobals(({ values }) => {
  values.set('userInfo', 'firebase-user');
  assert.equal(expireDemoSession(undefined), false);
  assert.equal(expireDemoSession(demoToken('missing')), false);
  assert.equal(values.get('userInfo'), 'firebase-user');
}));
