import { apiRequest } from '../services/apiClient';

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
