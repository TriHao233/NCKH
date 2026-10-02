import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('./apiClient.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
  .replace(/export /g, '');

function client({ demo = null, auth = null, responses }) {
  const calls = [];
  const expired = [];
  const events = [];
  const apiRequest = runInNewContext(`${source}\napiRequest`, {
    auth, FormData, Event,
    demoAuthHeaders: () => demo,
    handleDemoSessionResponse: (status, token) => expired.push({ status, token }),
    SESSION_EXPIRED_EVENT: 'qbank:session-expired',
    dispatchEvent: (event) => events.push(event.type),
    fetch: async (url, options) => {
      calls.push({ url, headers: { ...options.headers } });
      return responses.shift();
    },
  });
  return { apiRequest, calls, expired, events };
}

test('binary downloads use demo authentication and leave the file body unread', async () => {
  const response = new Response('%PDF-test', { headers: { 'Content-Type': 'application/pdf' } });
  const api = client({ demo: { Authorization: 'Bearer demo.test' }, responses: [response] });
  assert.equal(await api.apiRequest('/questions/id/source-pdf', { responseType: 'response' }), response);
  assert.equal(response.bodyUsed, false);
  assert.equal(await response.text(), '%PDF-test');
  assert.equal(api.calls[0].headers.Authorization, 'Bearer demo.test');
});

test('binary download 401 expires the rejected demo session', async () => {
  const api = client({ demo: { Authorization: 'Bearer demo.test' }, responses: [
    Response.json({ detail: 'Phiên hết hạn' }, { status: 401 }),
  ] });
  await assert.rejects(api.apiRequest('/file', { responseType: 'response' }), { status: 401, message: 'Phiên hết hạn' });
  assert.equal(api.expired[0].token, 'Bearer demo.test');
});

test('binary Firebase requests refresh an expired token and keep the returned file intact', async () => {
  const user = { uid: 'test-user', getIdToken: async (refresh) => refresh ? 'fresh' : 'old' };
  const file = new Response('docx-test');
  const api = client({ auth: { currentUser: user, authStateReady: async () => {} }, responses: [
    new Response('', { status: 401 }), file,
  ] });
  assert.equal(await api.apiRequest('/file', { responseType: 'response' }), file);
  assert.deepEqual(api.calls.map((call) => call.headers.Authorization), ['Bearer old', 'Bearer fresh']);
  assert.equal(file.bodyUsed, false);
  assert.deepEqual(api.events, []);
});

test('binary missing-file errors preserve the session and JSON requests still parse normally', async () => {
  const api = client({ demo: { Authorization: 'Bearer demo.test' }, responses: [
    Response.json({ detail: 'Không tìm thấy tệp' }, { status: 404 }), Response.json({ total: 3 }),
  ] });
  await assert.rejects(api.apiRequest('/file', { responseType: 'response' }), { status: 404 });
  assert.equal((await api.apiRequest('/questions')).total, 3);
  assert.deepEqual(api.expired, []);
});
