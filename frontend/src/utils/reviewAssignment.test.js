import test from 'node:test';
import assert from 'node:assert/strict';
import { assignmentReasonLabel, reviewerFlagLabel } from './reviewAssignment.js';
test('assignment reasons and reviewer flags have readable labels and preserve unknown errors', () => {
  for (const key of ['NO_REVIEWERS', 'NO_SUBJECT_SPECIALIST', 'NO_ELIGIBLE_REVIEWER']) assert.notEqual(assignmentReasonLabel(key), key);
  for (const key of ['HIGH_OVERRIDE', 'HIGH_BULK', 'SLA_BREACHED', 'NO_SUBJECTS']) assert.notEqual(reviewerFlagLabel(key), key);
  assert.equal(assignmentReasonLabel('custom error'), 'custom error'); assert.equal(reviewerFlagLabel('NEW'), 'NEW');
});
