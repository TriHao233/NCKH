import { apiRequest } from '../services/apiClient';

export function listQuestions({
  page = 1,
  pageSize = 20,
  reviewStatus,
  search,
  questionType,
  bloomLevel,
  documentId,
  qualityColor,
  minScore,
  publicationStatus,
  evaluationStatus,
} = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (reviewStatus) params.set('review_status', reviewStatus);
  if (search) params.set('search', search);
  if (questionType) params.set('question_type', questionType);
  if (bloomLevel) params.set('bloom_level', bloomLevel);
  if (documentId) params.set('document_id', documentId);
  if (qualityColor) params.set('quality_color', qualityColor);
  if (minScore !== undefined && minScore !== null && minScore !== '') params.set('min_score', minScore);
  if (publicationStatus) params.set('publication_status', publicationStatus);
  if (evaluationStatus) params.set('evaluation_status', evaluationStatus);
  return apiRequest(`/questions?${params.toString()}`);
}

export function getQuestion(id) {
  return apiRequest(`/questions/${id}`);
}

export function updateQuestion(id, payload) {
  return apiRequest(`/questions/${id}`, { method: 'PATCH', body: payload });
}

export function submitQuestionForReview(id) {
  return apiRequest(`/questions/${id}/submit-review`, { method: 'POST' });
}

export function deleteQuestion(id) {
  return apiRequest(`/questions/${id}`, { method: 'DELETE' });
}

export function autoEvaluateQuestion(id, payload) {
  return apiRequest(`/questions/${id}/evaluations/auto`, { method: 'POST', body: payload });
}

export function listQuestionEvaluations(id) {
  return apiRequest(`/questions/${id}/evaluations`);
}

export function reviewQuestion(id, payload) {
  return apiRequest(`/questions/${id}/reviews`, { method: 'POST', body: payload });
}

export function listQuestionReviews(id) {
  return apiRequest(`/questions/${id}/reviews`);
}

export function publishQuestionToMoodle(id, payload) {
  return apiRequest(`/questions/${id}/moodle-publications`, { method: 'POST', body: payload });
}

export function listQuestionMoodlePublications(id) {
  return apiRequest(`/questions/${id}/moodle-publications`);
}

export function exportQuestionMoodle(id, format = 'gift') {
  const params = new URLSearchParams({ format });
  return apiRequest(`/questions/${id}/moodle-export?${params.toString()}`);
}
