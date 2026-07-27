import test from 'node:test';
import assert from 'node:assert/strict';
import {
  QUESTION_BANK_EXPORT_COLUMNS,
  normalizeQuestionBankType,
  parseQuestionBankImportFile,
  parseQuestionBankImport,
  questionsToGift,
  questionsToMoodleXml,
  timestampedQuestionBankFilename,
} from './questionBankExchange.js';
import { rowsToXlsxBlob } from './csvExport.js';

const subject = {
  id: 'subject-1',
  subject_code: 'CS101',
  chapters: [
    { id: 'chapter-1', chapter_code: 'C1', chapter_name: 'Intro' },
  ],
  learning_outcomes: [
    { id: 'clo-1', clo_code: 'CLO1' },
    { id: 'clo-2', clo_code: 'CLO2' },
  ],
};

const question = {
  question_code: 'Q1',
  content: 'Pick one',
  review_status: 'APPROVED',
  publication_status: 'NOT_PUBLISHED',
  classification: {
    assessment_type: 'TRAC_NGHIEM',
    bloom: { level: 2 },
    difficulty: 'de',
    subject: { id: 'subject-1' },
    chapter: { id: 'chapter-1' },
  },
  clos: [{ id: 'clo-1', code: 'CLO1' }],
  sources: [{ chunk_id: 'chunk-1' }],
  question_data: {
    options: { A: 'Alpha', B: 'Beta' },
    correct_answer: 'A',
    explanation: 'Because Alpha is right',
  },
};

test('normalizes common import type aliases', () => {
  assert.equal(normalizeQuestionBankType('MCQ'), 'trac_nghiem');
  assert.equal(normalizeQuestionBankType('true false'), 'dung_sai');
  assert.equal(normalizeQuestionBankType('multiple_response'), 'nhieu_lua_chon');
});

test('question bank export columns flatten question metadata', () => {
  const row = Object.fromEntries(
    QUESTION_BANK_EXPORT_COLUMNS.map((column) => [column.header, column.value(question)]),
  );

  assert.equal(row.question_type, 'trac_nghiem');
  assert.equal(row.bloom_level, '2');
  assert.equal(row.subject_id, 'subject-1');
  assert.equal(row.clo_ids, 'clo-1');
  assert.deepEqual(row.options_json, { A: 'Alpha', B: 'Beta' });
});

test('questionsToGift writes Moodle GIFT choices and feedback', () => {
  const gift = questionsToGift([question]);

  assert.match(gift, /::Q1::Pick one/);
  assert.match(gift, /\{=Alpha ~Beta#Because Alpha is right\}/);
});

test('parseQuestionBankImport maps CSV rows to create payloads', () => {
  const csv = [
    'content,question_type,bloom_level,difficulty,subject_id,chapter_id,clo_ids,option_A,option_B,correct_answer,explanation',
    '"Pick one","mcq","3","trung_binh","CS101","C1","CLO1; CLO2","Alpha","Beta","A","Reason"',
  ].join('\r\n');
  const result = parseQuestionBankImport(csv, { filename: 'bank.csv', subjects: [subject] });

  assert.deepEqual(result.errors, []);
  assert.equal(result.items.length, 1);
  assert.deepEqual(result.items[0].payload, {
    content: 'Pick one',
    question_type: 'trac_nghiem',
    bloom_level: 3,
    difficulty: 'trung_binh',
    subject_id: 'subject-1',
    chapter_id: 'chapter-1',
    clo_ids: ['clo-1', 'clo-2'],
    source_chunk_ids: [],
    question_data: {
      options: { A: 'Alpha', B: 'Beta' },
      correct_answer: 'A',
      explanation: 'Reason',
    },
  });
});

test('parseQuestionBankImport reads GIFT multiple choice', () => {
  const gift = '::Q2::Choose values{~%50%Alpha ~%50%Beta ~%-100%Gamma}';
  const result = parseQuestionBankImport(gift, { filename: 'bank.gift' });

  assert.deepEqual(result.errors, []);
  assert.equal(result.items[0].payload.question_type, 'nhieu_lua_chon');
  assert.deepEqual(result.items[0].payload.question_data.options, {
    A: 'Alpha',
    B: 'Beta',
    C: 'Gamma',
  });
  assert.equal(result.items[0].payload.question_data.correct_answer, 'A, B');
});

test('parseQuestionBankImportFile reads XLSX rows', async () => {
  const blob = rowsToXlsxBlob(
    [
      { header: 'content', value: (row) => row.content },
      { header: 'question_type', value: (row) => row.questionType },
      { header: 'subject_id', value: (row) => row.subject },
      { header: 'option_A', value: (row) => row.optionA },
      { header: 'option_B', value: (row) => row.optionB },
      { header: 'correct_answer', value: (row) => row.correctAnswer },
    ],
    [
      {
        content: 'From spreadsheet',
        questionType: 'mcq',
        subject: 'CS101',
        optionA: 'Alpha',
        optionB: 'Beta',
        correctAnswer: 'B',
      },
    ],
    'Question bank',
  );
  const file = {
    name: 'bank.xlsx',
    arrayBuffer: () => blob.arrayBuffer(),
  };
  const result = await parseQuestionBankImportFile(file, { subjects: [subject] });

  assert.deepEqual(result.errors, []);
  assert.equal(result.items[0].payload.content, 'From spreadsheet');
  assert.equal(result.items[0].payload.subject_id, 'subject-1');
  assert.deepEqual(result.items[0].payload.question_data.options, { A: 'Alpha', B: 'Beta' });
  assert.equal(result.items[0].payload.question_data.correct_answer, 'B');
});

test('Moodle XML export can be imported back to payloads', () => {
  const xml = questionsToMoodleXml([question]);
  const result = parseQuestionBankImport(xml, { filename: 'bank.xml' });

  assert.deepEqual(result.errors, []);
  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].payload.content, 'Pick one');
  assert.equal(result.items[0].payload.question_type, 'trac_nghiem');
  assert.equal(result.items[0].payload.question_data.correct_answer, 'A');
});

test('timestampedQuestionBankFilename is stable with a provided clock', () => {
  const filename = timestampedQuestionBankFilename('question-bank', 'gift', new Date('2026-07-27T01:02:03.004Z'));

  assert.equal(filename, 'question-bank-2026-07-27T01-02-03-004Z.gift');
});
