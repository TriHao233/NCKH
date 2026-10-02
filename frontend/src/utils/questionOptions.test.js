import assert from 'node:assert/strict';
import test from 'node:test';
import { optionEntriesForQuestion, validateQuestionAnswer } from './questionOptions.js';

test('manual matching and ordering expose editable items before options exist', () => {
  assert.deepEqual(optionEntriesForQuestion({ questionType: 'ghep_cot' }).map((item) => item.key), ['1', '2', '3', 'a', 'b', 'c', 'd']);
  assert.deepEqual(optionEntriesForQuestion({ questionType: 'sap_xep' }).map((item) => item.key), ['A', 'B', 'C', 'D']);
  assert.match(validateQuestionAnswer({ questionType: 'sap_xep', correctAnswer: 'A, B, C, D' }), /không được để trống/);
});

test('ordering must include every actual step once', () => {
  const question = { questionType: 'sap_xep', rawOptions: { A: 'Nhập', B: 'Kiểm tra', C: 'Xử lý', D: 'Xuất' } };
  assert.equal(validateQuestionAnswer({ ...question, correctAnswer: 'A, B, C, D' }), null);
  for (const correctAnswer of ['A, B, C', 'A, B, C, C', 'A, B, C, E']) {
    assert.match(validateQuestionAnswer({ ...question, correctAnswer }), /mỗi khóa đúng một lần/);
  }
});

test('matching requires complete pairs and a distractor', () => {
  const question = { questionType: 'ghep_cot', rawOptions: { 1: 'Một', 2: 'Hai', 3: 'Ba', a: 'First', b: 'Second', c: 'Third', d: 'Fourth' } };
  assert.equal(validateQuestionAnswer({ ...question, correctAnswer: '1-a, 2-b, 3-c' }), null);
  for (const correctAnswer of ['1-a, 2-b', '1-a, 1-b, 3-c', '1-a, 2-b, 3-z']) {
    assert.match(validateQuestionAnswer({ ...question, correctAnswer }), /đủ cặp đáp án/);
  }
});
