import test from 'node:test';
import assert from 'node:assert/strict';
import { saveDemoSession, readDemoSession, expireDemoSession, handleDemoSessionResponse, DEMO_SESSION_EXPIRED_EVENT } from './demoSession.js';

function withStorage(run) {
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const values = new Map();
  const window = new EventTarget();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  } });
  Object.defineProperty(globalThis, 'window', { configurable: true, value: window });
  try { run({ values, window }); }
  finally {
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage);
    else delete globalThis.localStorage;
    if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow);
    else delete globalThis.window;
  }
}

test('invalid current demo session clears cached user and sends one expiry event', () => withStorage(({ values, window }) => {
  saveDemoSession('demo.current', { role: 'Reviewer' });
  values.set('userInfo', '{}');
  let events = 0;
  window.addEventListener(DEMO_SESSION_EXPIRED_EVENT, () => events++);
  assert.equal(handleDemoSessionResponse(401, 'Bearer demo.current'), true);
  assert.equal(readDemoSession(), null);
  assert.equal(values.has('userInfo'), false);
  assert.equal(handleDemoSessionResponse(401, 'Bearer demo.current'), false);
  assert.equal(events, 1);
}));

test('a late response for an old session cannot clear the new login', () => withStorage(({ values }) => {
  saveDemoSession('demo.new', { role: 'Admin' });
  values.set('userInfo', 'new-user');
  assert.equal(handleDemoSessionResponse(401, 'Bearer demo.old'), false);
  assert.equal(readDemoSession().token, 'demo.new');
  assert.equal(values.get('userInfo'), 'new-user');
}));

test('permission errors, server errors and Firebase failures leave demo state alone', () => withStorage(() => {
  saveDemoSession('demo.current', { role: 'Reviewer' });
  for (const status of [200, 403, 409, 500, 503]) assert.equal(handleDemoSessionResponse(status, 'Bearer demo.current'), false);
  assert.equal(handleDemoSessionResponse(401, 'Bearer firebase-token'), false);
  assert.equal(handleDemoSessionResponse(401, undefined), false);
  assert.equal(readDemoSession().token, 'demo.current');
}));

test('expiry without a matching session does not clear an unrelated cached user', () => withStorage(({ values }) => {
  values.set('userInfo', 'firebase-user');
  assert.equal(expireDemoSession(undefined), false);
  assert.equal(expireDemoSession('demo.missing'), false);
  assert.equal(values.get('userInfo'), 'firebase-user');
}));
