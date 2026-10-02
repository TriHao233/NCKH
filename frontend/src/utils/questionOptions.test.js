import test from 'node:test';
import assert from 'node:assert/strict';
import { optionEntriesForQuestion, validateQuestionAnswer } from './questionOptions.js';

test('structured editors provide empty steps and two matching columns', () => {
  assert.deepEqual(optionEntriesForQuestion({ questionType: 'sap_xep' }).map((item) => item.key), ['1', '2', '3', '4']);
  assert.deepEqual(optionEntriesForQuestion({ questionType: 'ghep_cot' }).map((item) => item.key), ['1', '2', '3', 'a', 'b', 'c', 'd']);
});

test('ordering answer is a complete permutation of the displayed steps', () => {
  const options = { 1: 'A', 2: 'B', 3: 'C', 4: 'D' };
  assert.equal(validateQuestionAnswer({ questionType: 'sap_xep', rawOptions: options, correctAnswer: '2, 4, 1, 3' }), null);
  assert.match(validateQuestionAnswer({ questionType: 'sap_xep', rawOptions: options, correctAnswer: '2, 2, 1, 3' }), /mỗi bước/);
});

test('matching answer uses each numbered item and distinct lettered items', () => {
  const options = { 1: 'A', 2: 'B', 3: 'C', a: 'X', b: 'Y', c: 'Z', d: 'Nhiễu' };
  assert.equal(validateQuestionAnswer({ questionType: 'ghep_cot', rawOptions: options, correctAnswer: '1-b, 2-a, 3-c' }), null);
  assert.match(validateQuestionAnswer({ questionType: 'ghep_cot', rawOptions: options, correctAnswer: '1-b, 2-b, 3-c' }), /khác nhau/);
});

test('structured answers reject missing items, unknown keys and insufficient options', () => {
  const steps = { A: 'Nhập', B: 'Kiểm tra', C: 'Xử lý', D: 'Xuất' };
  assert.equal(validateQuestionAnswer({ questionType: 'sap_xep', rawOptions: steps, correctAnswer: 'B, A, D, C' }), null);
  for (const correctAnswer of ['A, B, C', 'A, B, C, C', 'A, B, C, E']) {
    assert.match(validateQuestionAnswer({ questionType: 'sap_xep', rawOptions: steps, correctAnswer }), /mỗi bước/);
  }
  assert.match(validateQuestionAnswer({ questionType: 'sap_xep', rawOptions: { 1: 'A', 2: 'B', 3: 'C' }, correctAnswer: '1, 2, 3' }), /ít nhất 4 bước/);
  assert.match(validateQuestionAnswer({ questionType: 'sap_xep', correctAnswer: '1, 2, 3, 4' }), /không được để trống/);
  const pairs = { 1: 'Một', 2: 'Hai', 3: 'Ba', a: 'First', b: 'Second', c: 'Third', d: 'Fourth' };
  for (const correctAnswer of ['1-a, 2-b', '1-a, 1-b, 3-c', '1-a, 2-b, 3-z']) {
    assert.match(validateQuestionAnswer({ questionType: 'ghep_cot', rawOptions: pairs, correctAnswer }), /ghép mỗi mục/);
  }
  const { d: _distractor, ...withoutDistractor } = pairs;
  assert.match(validateQuestionAnswer({ questionType: 'ghep_cot', rawOptions: withoutDistractor, correctAnswer: '1-a, 2-b, 3-c' }), /gây nhiễu/);
});
