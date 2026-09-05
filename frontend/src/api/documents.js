import { apiRequest, ApiError } from '../services/apiClient';
import { auth } from '../firebase';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export function listDocuments({ page = 1, pageSize = 20, status, search } = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  return apiRequest(`/documents?${params.toString()}`);
}

export function getDocument(id) {
  return apiRequest(`/documents/${id}`);
}

export function listDocumentJobs(id, { limit = 20 } = {}) {
  const params = new URLSearchParams();
  params.set('limit', limit);
  return apiRequest(`/documents/${id}/jobs?${params.toString()}`);
}

export function listDocumentPages(id, { limit = 100 } = {}) {
  const params = new URLSearchParams();
  params.set('limit', limit);
  return apiRequest(`/documents/${id}/pages?${params.toString()}`);
}

export function updateDocumentPage(documentId, pageId, payload) {
  return apiRequest(`/documents/${documentId}/pages/${pageId}`, { method: 'PATCH', body: payload });
}

export async function fetchDocumentSource(documentId) {
  await auth.authStateReady();
  const firebaseUser = auth.currentUser;
  if (!firebaseUser) throw new ApiError('Bạn chưa đăng nhập', 401, null);
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/source`, {
    headers: { Authorization: `Bearer ${await firebaseUser.getIdToken()}` },
  });
  if (!response.ok) throw new ApiError('Không mở được tài liệu nguồn', response.status, null);
  return window.URL.createObjectURL(await response.blob());
}

export function retryDocumentJob(documentId, jobId) {
  return apiRequest(`/documents/${documentId}/jobs/${jobId}/retry`, { method: 'POST' });
}

export function cancelDocumentJob(documentId, jobId) {
  return apiRequest(`/documents/${documentId}/jobs/${jobId}/cancel`, { method: 'POST' });
}

export function reindexDocument(documentId) {
  return apiRequest(`/documents/${documentId}/reindex`, { method: 'POST' });
}

export function updateDocument(id, payload) {
  return apiRequest(`/documents/${id}`, { method: 'PATCH', body: payload });
}

export function updateDocumentSharing(id, payload) {
  return apiRequest(`/documents/${id}/sharing`, { method: 'PATCH', body: payload });
}

export function deleteDocument(id) {
  return apiRequest(`/documents/${id}`, { method: 'DELETE' });
}
