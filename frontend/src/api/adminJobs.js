import { apiRequest } from '../services/apiClient';

export function listAdminJobs({
  page = 1,
  pageSize = 30,
  kind,
  status,
  userId,
  staleOnly = false,
  search,
  dateFrom,
  dateTo,
} = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (kind && kind !== 'all') params.set('kind', kind);
  if (status && status !== 'all') params.set('status', status);
  if (userId) params.set('user_id', userId);
  if (staleOnly) params.set('stale_only', 'true');
  if (search) params.set('search', search);
  if (dateFrom) params.set('date_from', `${dateFrom}T00:00:00`);
  if (dateTo) params.set('date_to', `${dateTo}T23:59:59`);
  return apiRequest(`/admin/jobs?${params.toString()}`);
}

export function retryAdminJob(kind, jobId) {
  return apiRequest(`/admin/jobs/${kind}/${jobId}/retry`, { method: 'POST' });
}

export function cancelAdminJob(kind, jobId) {
  return apiRequest(`/admin/jobs/${kind}/${jobId}/cancel`, { method: 'POST' });
}
