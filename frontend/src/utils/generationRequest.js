export function buildGenerationRequest({
  documentId,
  questionPlan,
  teacherInstruction,
  targetHeading,
  topic,
  cloCodes,
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
    question_type: firstPlanItem.question_type,
    num_questions: firstPlanItem.num_questions,
    question_plan: questionPlan,
    instruction,
    ...(targetHeading?.trim() ? { target_heading: targetHeading.trim() } : {}),
    ...(topic?.trim() ? { topic: topic.trim() } : {}),
    clo_codes: cloCodes || [],
    retrieval_mode: 'hybrid',
    ...(modelProvider ? { model_provider: modelProvider } : {}),
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
