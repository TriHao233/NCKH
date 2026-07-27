import test from 'node:test';
import assert from 'node:assert/strict';

import {
  demoUsernameFor,
  isValidEmail,
  loginErrorMessage,
  normalizeLoginEmail,
  validateLoginIdentifier,
} from './loginIdentifier.js';

test('normalizes email identifiers before Firebase login', () => {
  assert.equal(normalizeLoginEmail('  Admin@QBankCTU.edu.vn '), 'admin@qbankctu.edu.vn');
  assert.equal(isValidEmail('teacher@ctu.edu.vn'), true);
  assert.equal(isValidEmail('admin'), false);
});

test('demo aliases only resolve when demo login is enabled', () => {
  assert.equal(demoUsernameFor('admin', true), 'admin');
  assert.equal(demoUsernameFor('reviewer@qbankctu.edu.vn', true), 'reviewer');
  assert.equal(demoUsernameFor('admin', false), null);
});

test('login identifier validation blocks non-email values before Firebase', () => {
  assert.equal(validateLoginIdentifier('teacher@ctu.edu.vn', false), '');
  assert.equal(validateLoginIdentifier('admin', true), '');
  assert.match(validateLoginIdentifier('admin', false), /email hợp lệ/);
  assert.match(validateLoginIdentifier('', true), /Vui lòng nhập/);
});

test('Firebase invalid-email is converted to a user-facing login message', () => {
  assert.match(
    loginErrorMessage({ code: 'auth/invalid-email', message: 'Firebase raw message' }, false),
    /Email không hợp lệ/,
  );
  assert.equal(
    loginErrorMessage({ code: 'auth/wrong-password' }, false),
    'Email hoặc mật khẩu không chính xác!',
  );
});
