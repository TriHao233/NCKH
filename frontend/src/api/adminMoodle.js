import { apiRequest } from '../services/apiClient';

export function listMoodleTargets({ includeInactive = true } = {}) {
  const params = new URLSearchParams();
  params.set('include_inactive', includeInactive ? 'true' : 'false');
  return apiRequest(`/admin/moodle/targets?${params.toString()}`);
}

export function saveMoodleTarget(payload) {
  return apiRequest('/admin/moodle/targets', { method: 'POST', body: payload });
}

export function checkMoodleTarget(targetId) {
  return apiRequest(`/admin/moodle/targets/${targetId}/check`, { method: 'POST' });
}

export function deactivateMoodleTarget(targetId) {
  return apiRequest(`/admin/moodle/targets/${targetId}`, { method: 'DELETE' });
}

export function listMoodlePublications({
  page = 1,
  pageSize = 30,
  status,
  siteKey,
  search,
} = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (status && status !== 'all') params.set('status', status);
  if (siteKey && siteKey !== 'all') params.set('site_key', siteKey);
  if (search) params.set('search', search);
  return apiRequest(`/admin/moodle/publications?${params.toString()}`);
}

export function retryMoodlePublication(publicationId) {
  return apiRequest(`/admin/moodle/publications/${publicationId}/retry`, { method: 'POST' });
}
