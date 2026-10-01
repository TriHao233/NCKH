import { apiRequest } from '../services/apiClient';

export function getAdminOverview() {
  return apiRequest('/admin/overview');
}

export function listAdminDocuments({ page = 1, pageSize = 20, status = '', search = '' } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  return apiRequest(`/admin/overview/documents?${params.toString()}`);
}
