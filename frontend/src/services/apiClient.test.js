import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { saveDemoSession, readDemoSession } from '../auth/demoSession.js';

let moduleId = 0;
async function loadClient(auth) {
  globalThis.__apiTestAuth = auth;
  const demoUrl = new URL('../auth/demoSession.js', import.meta.url).href;
  let source = await readFile(new URL('./apiClient.js', import.meta.url), 'utf8');
  source = source.replace('import { auth } from "../firebase";', 'const auth = globalThis.__apiTestAuth;')
    .replace('"../auth/demoSession"', JSON.stringify(demoUrl))
    .replace('import.meta.env.VITE_API_BASE_URL', 'undefined');
  return import(`data:text/javascript;base64,${Buffer.from(`${source}\n// ${moduleId++}`).toString('base64')}`);
}

async function withGlobals(run) {
  const originalFetch = globalThis.fetch;
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const originalDispatch = Object.getOwnPropertyDescriptor(globalThis, 'dispatchEvent');
  const values = new Map();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  } });
  globalThis.dispatchEvent = () => true;
  try { await run(); } finally {
    globalThis.fetch = originalFetch;
    if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage);
    else delete globalThis.localStorage;
    if (originalDispatch) Object.defineProperty(globalThis, 'dispatchEvent', originalDispatch);
    else delete globalThis.dispatchEvent;
    delete globalThis.__apiTestAuth;
  }
}

test('binary downloads accept demo login and preserve bytes', () => withGlobals(async () => {
  const token = `demo.${Buffer.from(JSON.stringify({ exp: Date.now() / 1000 + 3600 })).toString('base64url')}.sig`;
  saveDemoSession(token, { role: 'Admin' });
  const bytes = new Uint8Array([0, 255, 128, 13, 10]);
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.Authorization, `Bearer ${token}`);
    return new Response(bytes, { headers: { 'content-type': 'application/pdf' } });
  };
  const { apiRequest } = await loadClient(null);
  assert.deepEqual(new Uint8Array(await (await apiRequest('/export/pdf', { responseType: 'blob' })).arrayBuffer()), bytes);
}));

test('binary downloads retry expired Firebase tokens through the shared request flow', () => withGlobals(async () => {
  const user = { uid: 'test-user', getIdToken: async (refresh) => refresh ? 'renewed' : 'expired' };
  const auth = { currentUser: user, authStateReady: async () => {} };
  let requests = 0;
  globalThis.fetch = async (_url, options) => {
    requests += 1;
    if (requests === 1) return new Response('{"detail":"expired"}', { status: 401 });
    assert.equal(options.headers.Authorization, 'Bearer renewed');
    return new Response(new Uint8Array([80, 75]), { headers: { 'content-type': 'application/octet-stream' } });
  };
  const { apiRequest } = await loadClient(auth);
  assert.equal((await apiRequest('/export/docx', { responseType: 'blob' })).size, 2);
  assert.equal(requests, 2);
}));

test('failed binary downloads retain API error details and expire rejected demo sessions', () => withGlobals(async () => {
  const token = `demo.${Buffer.from(JSON.stringify({ exp: Date.now() / 1000 + 3600 })).toString('base64url')}.sig`;
  saveDemoSession(token, { role: 'Admin' });
  globalThis.fetch = async () => new Response('{"detail":"Phiên đăng nhập hết hạn"}', {
    status: 401, headers: { 'content-type': 'application/json' },
  });
  const { apiRequest } = await loadClient(null);
  await assert.rejects(apiRequest('/export/pdf', { responseType: 'blob' }), /Phiên đăng nhập hết hạn/);
  assert.equal(readDemoSession(), null);
}));
