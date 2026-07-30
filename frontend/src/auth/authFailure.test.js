import test from 'node:test';
import assert from 'node:assert/strict';

import { authFailureFor } from './authFailure.js';

test('401 ends the session with a clear login message', () => {
  const result = authFailureFor(401, { detail: 'Token expired' });
  assert.equal(result.status, 401);
  assert.match(result.message, /hết hạn/i);
});

test('account-disabled 403 ends the session', () => {
  assert.deepEqual(
    authFailureFor(403, { detail: 'Tài khoản đã bị khóa' }),
    { status: 403, message: 'Tài khoản đã bị khóa' },
  );
});

test('ordinary authorization 403 keeps the current session', () => {
  assert.equal(
    authFailureFor(403, { detail: 'Bạn không có quyền thực hiện thao tác này' }),
    null,
  );
});
