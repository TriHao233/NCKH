import { apiRequest } from '../services/apiClient';

export function getCatalogOverview() {
  return apiRequest('/catalog/overview');
}

export function listSubjects() {
  return apiRequest('/catalog/subjects');
}

export function saveSubject(payload) {
  return apiRequest('/catalog/subjects', { method: 'POST', body: payload });
}

export function updateSubject(subjectId, payload) {
  return apiRequest(`/catalog/subjects/${subjectId}`, { method: 'PATCH', body: payload });
}

export function addSubjectChapter(subjectId, payload) {
  return apiRequest(`/catalog/subjects/${subjectId}/chapters`, { method: 'POST', body: payload });
}

export function updateSubjectChapter(subjectId, chapterId, payload) {
  return apiRequest(`/catalog/subjects/${subjectId}/chapters/${chapterId}`, { method: 'PATCH', body: payload });
}

export function addSubjectLearningOutcome(subjectId, payload) {
  return apiRequest(`/catalog/subjects/${subjectId}/learning-outcomes`, { method: 'POST', body: payload });
}

export function updateSubjectLearningOutcome(subjectId, cloId, payload) {
  return apiRequest(`/catalog/subjects/${subjectId}/learning-outcomes/${cloId}`, { method: 'PATCH', body: payload });
}

export function listAiModels() {
  return apiRequest('/catalog/ai-models');
}

export function saveAiModel(payload) {
  return apiRequest('/catalog/ai-models', { method: 'POST', body: payload });
}

export function listPromptTemplates() {
  return apiRequest('/catalog/prompt-templates');
}

export function savePromptTemplate(payload) {
  return apiRequest('/catalog/prompt-templates', { method: 'POST', body: payload });
}

export function listEvaluationPolicies() {
  return apiRequest('/catalog/evaluation-policies');
}

export function saveEvaluationPolicy(payload) {
  return apiRequest('/catalog/evaluation-policies', { method: 'POST', body: payload });
}
