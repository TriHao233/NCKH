import { apiRequest } from '../services/apiClient';

export function listQuestions({ page = 1, pageSize = 20, reviewStatus, search } = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (reviewStatus) params.set('review_status', reviewStatus);
  if (search) params.set('search', search);
  return apiRequest(`/questions?${params.toString()}`);
}

export function getQuestion(id) {
  return apiRequest(`/questions/${id}`);
}

export function updateQuestion(id, payload) {
  return apiRequest(`/questions/${id}`, { method: 'PATCH', body: payload });
}

export function deleteQuestion(id) {
  return apiRequest(`/questions/${id}`, { method: 'DELETE' });
}
