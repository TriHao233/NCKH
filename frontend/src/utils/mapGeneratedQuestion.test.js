import assert from 'node:assert/strict';
import test from 'node:test';

import { mapGeneratedQuestions } from './mapGeneratedQuestion.js';


test('maps post-processing evidence metadata for generated drafts', () => {
  const [question] = mapGeneratedQuestions([
    {
      question_id: 'q-1',
      question: 'Ngăn xếp (Stack) tuân theo nguyên tắc FIFO.',
      options: { A: 'Đúng', B: 'Sai' },
      correct_answer: 'B',
      explanation: 'Ngăn xếp dùng LIFO.',
      question_type: 'dung_sai',
      bloom_level: '2_hieu',
      source_context: 'Ngăn xếp (Stack) dùng LIFO.',
      source_keywords: ['Ngăn xếp (Stack)'],
      false_mutation: {
        field: 'relation',
        original: 'LIFO',
        replacement: 'FIFO',
      },
    },
  ]);

  assert.deepEqual(question.sourceKeywords, ['Ngăn xếp (Stack)']);
  assert.equal(question.falseMutation.original, 'LIFO');
  assert.equal(question.falseMutation.replacement, 'FIFO');
});
