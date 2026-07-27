export const BULK_QUESTION_CHANGE_NOTE = 'Bulk edit from ManagePage';

export function selectedQuestionsForIds(questions = [], selectedIds = []) {
  const selected = new Set(selectedIds);
  return questions.filter((question) => selected.has(question.id));
}

export function filterSubmittableQuestions(questions = [], submittableStatuses = new Set()) {
  return questions.filter((question) => submittableStatuses.has(question.review_status));
}

export function buildBulkQuestionUpdatePayload(question, draft = {}) {
  if (!question?.current_version) return null;
  const payload = {
    expected_version: question.current_version,
    change_note: BULK_QUESTION_CHANGE_NOTE,
  };
  if (draft.bloomLevel) {
    payload.bloom_level = Number(draft.bloomLevel);
  }
  if (draft.difficulty) {
    payload.difficulty = draft.difficulty;
  }
  if (draft.applyClo) {
    payload.clo_ids = Array.isArray(draft.cloIds) ? draft.cloIds : [];
  }
  return Object.keys(payload).length > 2 ? payload : null;
}

export function summarizeBulkSettled(results = []) {
  return results.reduce(
    (summary, result) => {
      if (result.status === 'fulfilled') {
        summary.success += 1;
      } else {
        summary.failed += 1;
        if (!summary.firstError) {
          summary.firstError = result.reason?.message || 'Thao tác thất bại';
        }
      }
      return summary;
    },
    { success: 0, failed: 0, firstError: '' },
  );
}
