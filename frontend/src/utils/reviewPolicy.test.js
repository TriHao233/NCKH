import test from 'node:test';
import assert from 'node:assert/strict';
import { scoreToPercent, percentToScore } from './reviewPolicy.js';
test('policy percentage round trips, blank disables, bounds validate', () => {
  assert.equal(scoreToPercent(null), ''); assert.equal(percentToScore(''), null);
  assert.equal(percentToScore('  '), null);
  for (const value of [0, 0.65, 0.333333, 1]) assert.equal(percentToScore(scoreToPercent(value)), value);
  for (const value of ['bad', '-1', '101', 'Infinity']) assert.throws(() => percentToScore(value));
});
