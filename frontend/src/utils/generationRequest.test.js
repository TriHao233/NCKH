import assert from 'node:assert/strict';
import test from 'node:test';

import { buildGenerationRequest, isDocumentIndexed, isDocumentOcrReady } from './generationRequest.js';

test('READY metadata alone cannot skip OCR or indexing', () => {
  assert.equal(isDocumentOcrReady({ status: 'READY', page_count: 1 }), false);
  assert.equal(isDocumentIndexed({ status: 'READY' }), false);
  const pipeline_summary = { ocr_status: 'COMPLETED', chunk_status: 'COMPLETED', index_status: 'COMPLETED' };
  assert.equal(isDocumentOcrReady({ pipeline_summary }), true);
  assert.equal(isDocumentIndexed({ pipeline_summary }), false);
  assert.equal(isDocumentIndexed({ pipeline_summary, current_processing: { chunk_set_id: 'chunks', vector_collection_id: 'vectors' } }), true);
});

test('a failed pipeline is never offered as a reusable generation source', () => {
  const document = {
    status: 'READY', page_count: 1,
    current_processing: { ocr_job_id: 'ocr', chunk_set_id: 'chunks', vector_collection_id: 'vectors' },
    pipeline_summary: { ocr_status: 'COMPLETED', chunk_status: 'COMPLETED', index_status: 'FAILED' },
  };
  assert.equal(isDocumentOcrReady(document), false);
  assert.equal(isDocumentIndexed(document), false);
});

test('buildGenerationRequest uses backend defaults and keeps instruction separate from heading', () => {
  const questionPlan = [{
    bloom_level: '2_hieu',
    difficulty: 'kho',
    question_type: 'dung_sai',
    num_questions: 3,
  }];
  const payload = buildGenerationRequest({
    documentId: 'document-1',
    questionPlan,
    teacherInstruction: '  Tập trung vào định nghĩa  ',
    targetHeading: '  Chương 3 - Hàng đợi  ',
    sourceMode: 'existing',
    modelProvider: 'qwen-fast',
    timings: { documentMs: 'reused', uploadMs: 10, ocrMs: 20, chunkMs: 30 },
    pipelineStartedAt: 100,
    now: () => 225.4,
  });

  assert.equal(payload.instruction, 'Tập trung vào định nghĩa');
  assert.equal(payload.model_provider, 'qwen-fast');
  assert.equal(payload.code_model_provider, 'qwen-fast');
  assert.equal(payload.difficulty, 'kho');
  assert.equal(payload.collection_name, undefined);
  assert.equal(payload.target_heading, 'Chương 3 - Hàng đợi');
  assert.equal(payload.client_telemetry.document_reused, true);
  assert.equal(payload.client_telemetry.elapsed_before_generate_ms, 125);
  assert.deepEqual(payload.question_plan, questionPlan);
});
