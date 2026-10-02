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
