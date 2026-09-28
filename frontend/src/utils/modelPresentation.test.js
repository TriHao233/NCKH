import test from 'node:test';
import assert from 'node:assert/strict';
import { modelPresentation } from './modelPresentation.js';

test('Qwen has one readable name without repeating its model identifier', () => {
  const model = { code: 'qwen3-8b', name: 'Qwen3 (8B)', version: 'qwen3:8b' };
  const result = modelPresentation(model);
  assert.equal(result.label, 'Qwen 3 (8B)');
  assert.equal(result.detail, '');
  assert.equal(result.family, 'qwen');
  assert.equal(model.code, 'qwen3-8b');
});

test('Gemini version is used when the supplied name is only the family', () => {
  assert.equal(modelPresentation({ name: 'Gemini', version: 'gemini-3.6-flash' }).label, 'Gemini 3.6 Flash');
  assert.equal(modelPresentation({ name: 'Gemini 3.6 Flash', version: 'gemini-3.6-flash' }).detail, '');
});

test('different versions and unfamiliar models keep their supplied identities', () => {
  assert.equal(modelPresentation({ name: 'Gemini 3 Flash', version: 'gemini-3.6-flash' }).detail, 'Gemini 3.6 Flash');
  assert.equal(modelPresentation({ name: 'Custom Model' }).label, 'Custom Model');
  assert.equal(modelPresentation().label, 'Mô hình mặc định');
});
