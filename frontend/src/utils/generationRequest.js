function documentHasFailedPipeline(document) {
  const pipeline = document?.pipeline_summary || {};
  return [document?.status, pipeline.ocr_status, pipeline.chunk_status, pipeline.index_status]
    .some((status) => ['FAILED', 'CANCELLED', 'ARCHIVED'].includes(String(status || '').toUpperCase()));
}

export function isDocumentOcrReady(document) {
  if (documentHasFailedPipeline(document)) return false;
  return String(document?.pipeline_summary?.ocr_status || '').toUpperCase() === 'COMPLETED'
    || Boolean(document?.current_processing?.ocr_job_id && Number(document?.page_count) > 0);
}

export function isDocumentIndexed(document) {
  if (documentHasFailedPipeline(document)) return false;
  const pipeline = document?.pipeline_summary || {};
  const current = document?.current_processing || {};
  return Boolean(current.chunk_set_id && current.vector_collection_id)
    && String(pipeline.chunk_status || '').toUpperCase() === 'COMPLETED'
    && String(pipeline.index_status || '').toUpperCase() === 'COMPLETED';
}

export function buildGenerationRequest({
  documentId,
  questionPlan,
  teacherInstruction,
  targetHeading,
  sourceMode,
  modelProvider,
  timings,
  pipelineStartedAt,
  now,
}) {
  const firstPlanItem = questionPlan[0];
  const instruction = teacherInstruction.trim() || undefined;

  return {
    document_id: documentId,
    bloom_level: firstPlanItem.bloom_level,
    difficulty: firstPlanItem.difficulty,
    question_type: firstPlanItem.question_type,
    num_questions: firstPlanItem.num_questions,
    question_plan: questionPlan,
    instruction,
    ...(targetHeading?.trim() ? { target_heading: targetHeading.trim() } : {}),
    ...(modelProvider ? { model_provider: modelProvider, code_model_provider: modelProvider } : {}),
    client_telemetry: {
      source_mode: sourceMode,
      document_reused: timings.documentMs === 'reused',
      upload_ms: timings.uploadMs,
      ocr_ms: timings.ocrMs,
      chunk_ms: timings.chunkMs,
      elapsed_before_generate_ms: Math.round(now() - pipelineStartedAt),
    },
  };
}
