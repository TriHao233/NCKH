import { auth } from '../../firebase';
import { apiRequest, ApiError } from '../services/apiClient';

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || '/api/v1'
).replace(/\/$/, '');

export function listQuestions({
  page = 1,
  pageSize = 20,
  reviewStatus,
  search,
  questionType,
  bloomLevel,
  documentId,
  subjectId,
  chapterId,
  cloId,
  difficulty,
  qualityColor,
  minScore,
  publicationStatus,
  evaluationStatus,
  assignmentStatus,
  assignedTo,
  creatorUserId,
  waitingHoursMin,
  overdueOnly = false,
} = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (reviewStatus) params.set('review_status', reviewStatus);
  if (search) params.set('search', search);
  if (questionType) params.set('question_type', questionType);
  if (bloomLevel) params.set('bloom_level', bloomLevel);
  if (documentId) params.set('document_id', documentId);
  if (subjectId) params.set('subject_id', subjectId);
  if (chapterId) params.set('chapter_id', chapterId);
  if (cloId) params.set('clo_id', cloId);
  if (difficulty) params.set('difficulty', difficulty);
  if (qualityColor) params.set('quality_color', qualityColor);
  if (minScore !== undefined && minScore !== null && minScore !== '') params.set('min_score', minScore);
  if (publicationStatus) params.set('publication_status', publicationStatus);
  if (evaluationStatus) params.set('evaluation_status', evaluationStatus);
  if (assignmentStatus) params.set('assignment_status', assignmentStatus);
  if (assignedTo) params.set('assigned_to', assignedTo);
  if (creatorUserId) params.set('creator_user_id', creatorUserId);
  if (waitingHoursMin) params.set('waiting_hours_min', waitingHoursMin);
  if (overdueOnly) params.set('overdue_only', 'true');
  return apiRequest(`/questions?${params.toString()}`);
}

export function getQuestion(id) {
  return apiRequest(`/questions/${id}`);
}

export function getQuestionSources(id) {
  return apiRequest(`/questions/${id}/sources`);
}

function filenameFromDisposition(disposition) {
  const match = disposition?.match(/filename="?([^";]+)"?/i);
  return match?.[1] || 'source.pdf';
}

export async function fetchQuestionSourcePdf(id) {
  await auth.authStateReady();
  const firebaseUser = auth.currentUser;
  if (!firebaseUser) {
    throw new ApiError('Bạn chưa đăng nhập', 401, null);
  }
  const response = await fetch(`${API_BASE_URL}/questions/${id}/source-pdf`, {
    headers: {
      Authorization: `Bearer ${await firebaseUser.getIdToken()}`,
    },
  });
  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      // Keep the fallback message below if the PDF endpoint returns plain text.
    }
    throw new ApiError(payload?.detail || 'Không mở được PDF nguồn', response.status, payload);
  }
  const blob = await response.blob();
  return {
    url: window.URL.createObjectURL(blob),
    filename: filenameFromDisposition(response.headers.get('content-disposition')),
  };
}

export function createQuestion(payload) {
  return apiRequest('/questions', { method: 'POST', body: payload });
}

export function duplicateQuestion(id) {
  return apiRequest(`/questions/${id}/duplicate`, { method: 'POST' });
}

export function updateQuestion(id, payload) {
  return apiRequest(`/questions/${id}`, { method: 'PATCH', body: payload });
}

export function updateQuestionSharing(id, payload) {
  return apiRequest(`/questions/${id}/sharing`, { method: 'PATCH', body: payload });
}

export function listQuestionVersions(id) {
  return apiRequest(`/questions/${id}/versions`);
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

export function claimQuestionReview(id) {
  return apiRequest(`/questions/${id}/review-assignment/claim`, { method: 'POST' });
}

export function releaseQuestionReview(id) {
  return apiRequest(`/questions/${id}/review-assignment/release`, { method: 'POST' });
}

export function assignQuestionReview(id, payload) {
  return apiRequest(`/questions/${id}/review-assignment`, { method: 'POST', body: payload });
}

export function listQuestionReviews(id) {
  return apiRequest(`/questions/${id}/reviews`);
}

export function listQuestionComments(id) {
  return apiRequest(`/questions/${id}/comments`);
}

export function addQuestionComment(id, payload) {
  return apiRequest(`/questions/${id}/comments`, { method: 'POST', body: payload });
}

export function setQuestionSecondaryReview(id, payload) {
  return apiRequest(`/questions/${id}/secondary-review`, { method: 'POST', body: payload });
}

export function getReviewDashboard() {
  return apiRequest('/questions/review-dashboard');
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
