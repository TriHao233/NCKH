import test from 'node:test';
import assert from 'node:assert/strict';
import { renewIntervalMs, shouldRenewLock } from './reviewLock.js';

const now = Date.parse('2026-09-30T06:00:00Z');

function input(remainingMinutes = 5) {
  return {
    question: {
      review_status: 'PENDING',
      review_assignment: {
        status: 'IN_REVIEW',
        reviewer_user_id: '1',
        lock_expires_at: new Date(now + remainingMinutes * 60000).toISOString(),
      },
    },
    userId: '1',
    now,
    lastActivityAt: now,
    timeoutMinutes: 30,
    visible: true,
  };
}

test('renew once a third of the lock has elapsed, when expired, and keep the interval floor', () => {
  assert.equal(shouldRenewLock(input()), true);
  assert.equal(shouldRenewLock(input(-1)), true);
  assert.equal(shouldRenewLock(input(20)), true);
  assert.equal(shouldRenewLock(input(25)), false);
  assert.equal(renewIntervalMs(30), 600000);
  assert.equal(renewIntervalMs(1), 60000);
});

test('do not renew other users, hidden or inactive tabs and finished questions', () => {
  for (const changes of [{ userId: '2' }, { userId: null }, { visible: false }, { lastActivityAt: now - 31 * 60000 }]) {
    assert.equal(shouldRenewLock({ ...input(), ...changes }), false);
  }
  for (const status of ['ASSIGNED', 'UNASSIGNED']) {
    const data = input();
    data.question.review_assignment.status = status;
    assert.equal(shouldRenewLock(data), false);
  }
  const done = input();
  done.question.review_status = 'APPROVED';
  assert.equal(shouldRenewLock(done), false);
  const invalid = input();
  invalid.question.review_assignment.lock_expires_at = 'bad';
  assert.equal(shouldRenewLock(invalid), false);
});

test('an active reviewer never gets closer than a third of the lock to expiry', () => {
  for (const timeoutMinutes of [3, 30, 45]) {
    const duration = timeoutMinutes * 60000;
    const step = renewIntervalMs(timeoutMinutes);
    const timerDelay = 250;
    const requestLatency = 400;
    let expires = duration; // nhận câu tại t = 0
    let renewals = 0;
    for (let tick = 1; tick <= 12; tick += 1) {
      const at = tick * step + timerDelay;
      assert.ok(expires - at >= duration / 3 - timerDelay, `tick ${tick}: lock too close to expiry`);
      const question = {
        review_status: 'PENDING',
        review_assignment: { status: 'IN_REVIEW', reviewer_user_id: '1', lock_expires_at: new Date(expires).toISOString() },
      };
      if (shouldRenewLock({ question, userId: '1', now: at, lastActivityAt: at, timeoutMinutes, visible: true })) {
        expires = at + requestLatency + duration;
        renewals += 1;
      }
    }
    assert.ok(renewals >= 6, `expected a renewal at least every second tick, got ${renewals}`);
  }
});
