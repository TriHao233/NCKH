import { apiRequest } from '../services/apiClient';

export function getAdminOverview() {
  return apiRequest('/admin/overview');
}

export function listAdminDocuments({ page = 1, pageSize = 20, status = '', search = '', subjectId = '', ownerId = '' } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  if (subjectId) params.set('subject_id', subjectId);
  if (ownerId) params.set('owner_id', ownerId);
  return apiRequest(`/admin/overview/documents?${params.toString()}`);
}
