import assert from 'node:assert/strict';
import test from 'node:test';

import { buildGenerationRequest } from './generationRequest.js';

test('buildGenerationRequest uses backend defaults and keeps instruction separate from heading', () => {
  const questionPlan = [{ bloom_level: '2_hieu', question_type: 'dung_sai', num_questions: 3 }];
  const payload = buildGenerationRequest({
    documentId: 'document-1',
    questionPlan,
    teacherInstruction: '  Tập trung vào định nghĩa  ',
    targetHeading: '  Chương 3 - Hàng đợi  ',
    topic: '  FIFO và enqueue  ',
    cloCodes: ['CLO2'],
    sourceMode: 'existing',
    modelProvider: 'qwen-fast',
    timings: { documentMs: 'reused', uploadMs: 10, ocrMs: 20, chunkMs: 30 },
    pipelineStartedAt: 100,
    now: () => 225.4,
  });

  assert.equal(payload.instruction, 'Tập trung vào định nghĩa');
  assert.equal(payload.model_provider, 'qwen-fast');
  assert.equal(payload.collection_name, undefined);
  assert.equal(payload.target_heading, 'Chương 3 - Hàng đợi');
  assert.equal(payload.topic, 'FIFO và enqueue');
  assert.deepEqual(payload.clo_codes, ['CLO2']);
  assert.equal(payload.retrieval_mode, 'hybrid');
  assert.equal(payload.client_telemetry.document_reused, true);
  assert.equal(payload.client_telemetry.elapsed_before_generate_ms, 125);
  assert.deepEqual(payload.question_plan, questionPlan);
});
