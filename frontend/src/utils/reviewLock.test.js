import test from 'node:test';
import assert from 'node:assert/strict';
import { renewIntervalMs, shouldRenewLock } from './reviewLock.js';
const now = Date.parse('2026-09-30T06:00:00Z');
function input(remainingMinutes = 5) { return { question: { review_status: 'PENDING', review_assignment: { status: 'IN_REVIEW', reviewer_user_id: '1', lock_expires_at: new Date(now + remainingMinutes * 60000).toISOString() } }, userId: '1', now, lastActivityAt: now, timeoutMinutes: 30, visible: true }; }
test('renew near expiry, expired and interval floor', () => {
  assert.equal(shouldRenewLock(input()), true);
  assert.equal(shouldRenewLock(input(-1)), true);
  assert.equal(shouldRenewLock(input(20)), false);
  assert.equal(renewIntervalMs(30), 600000); assert.equal(renewIntervalMs(1), 60000);
});
test('do not renew other users, hidden or inactive tabs and finished questions', () => {
  for (const changes of [{ userId: '2' }, { userId: null }, { visible: false }, { lastActivityAt: now - 31 * 60000 }]) assert.equal(shouldRenewLock({ ...input(), ...changes }), false);
  for (const status of ['ASSIGNED', 'UNASSIGNED']) { const data = input(); data.question.review_assignment.status = status; assert.equal(shouldRenewLock(data), false); }
  const done = input(); done.question.review_status = 'APPROVED'; assert.equal(shouldRenewLock(done), false);
  const invalid = input(); invalid.question.review_assignment.lock_expires_at = 'bad'; assert.equal(shouldRenewLock(invalid), false);
});
