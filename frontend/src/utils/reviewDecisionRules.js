export const AI_BUSY_STATUSES = Object.freeze(['QUEUED', 'PROCESSING', 'RUNNING']);
export function overrideRequired(question, decision) {
  return decision === 'APPROVED' && question?.evaluation_status === 'FAILED';
}
export function isAiRunning(question) {
  return AI_BUSY_STATUSES.includes(question?.evaluation_status);
}
export function selfReviewReasonRequired(question, user) {
  return user?.role === 'Admin' && Boolean(user.id)
    && (question?.author_user_ids || []).map(String).includes(String(user.id));
}
