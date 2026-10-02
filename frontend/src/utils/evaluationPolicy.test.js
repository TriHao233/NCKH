import test from 'node:test';
import assert from 'node:assert/strict';
import {
  describePolicyChanges,
  formToPayload,
  policyToForm,
  validatePolicyForm,
  weightTotal,
} from './evaluationPolicy.js';

const POLICY = {
  policy_name: 'Default question quality policy',
  weights: { faithfulness: 0.35, contextual_relevancy: 0.2, answer_relevancy: 0.15, bloom_alignment: 0.15, clo_alignment: 0.15 },
  thresholds: { yellow_min: 0.5, pass_min: 0.7, green_min: 0.75 },
};

test('policy form round trips weights as percent and thresholds as scores', () => {
  const form = policyToForm(POLICY);
  assert.equal(form.weights.faithfulness, '35');
  assert.equal(weightTotal(form), 100);
  assert.equal(validatePolicyForm(form), '');
  assert.deepEqual(formToPayload(form), POLICY);
});

test('policy form keeps weight keys the page does not know', () => {
  const form = policyToForm({ ...POLICY, weights: { ...POLICY.weights, custom_metric: 0 } });
  assert.equal(form.weights.custom_metric, '0');
  assert.equal(formToPayload(form).weights.custom_metric, 0);
});

test('policy form rejects a wrong total, bad numbers and out-of-order thresholds', () => {
  const form = policyToForm(POLICY);
  assert.match(validatePolicyForm({ ...form, weights: { ...form.weights, faithfulness: '40' } }), /Tổng trọng số/);
  assert.match(validatePolicyForm({ ...form, weights: { ...form.weights, faithfulness: '' } }), /Bám sát nguồn/);
  assert.match(validatePolicyForm({ ...form, thresholds: { ...form.thresholds, pass_min: '0.8' } }), /thứ tự/);
  assert.match(validatePolicyForm({ ...form, thresholds: { ...form.thresholds, pass_min: '' } }), /từ 0 đến 1/);
  assert.match(validatePolicyForm({ ...form, policy_name: ' ' }), /tên/);
});

test('policy changes list only what differs from the previous version', () => {
  const previous = { ...POLICY, thresholds: { ...POLICY.thresholds, pass_min: 0.65 } };
  assert.deepEqual(describePolicyChanges(previous, POLICY), ['Điểm đạt: 0.65 → 0.70']);
  assert.deepEqual(describePolicyChanges(null, POLICY), []);
  const reweighted = { ...POLICY, weights: { ...POLICY.weights, faithfulness: 0.4, clo_alignment: 0.1 } };
  assert.deepEqual(describePolicyChanges(POLICY, reweighted), ['Bám sát nguồn: 35% → 40%', 'Đúng CLO: 15% → 10%']);
});
