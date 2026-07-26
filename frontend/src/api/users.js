import { apiRequest } from '../services/apiClient';

export function listUsers({ page = 1, pageSize = 20, role, search } = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (role) params.set('role', role);
  if (search) params.set('search', search);
  return apiRequest(`/users?${params.toString()}`);
}

export function getUser(id) {
  return apiRequest(`/users/${id}`);
}

export function createUser(payload) {
  return apiRequest('/users', { method: 'POST', body: payload });
}

export function updateUser(id, payload) {
  return apiRequest(`/users/${id}`, { method: 'PATCH', body: payload });
}

export function deleteUser(id) {
  return apiRequest(`/users/${id}`, { method: 'DELETE' });
}

export function listGenerationPresets() {
  return apiRequest('/users/me/generation-presets');
}

export function saveGenerationPreset(payload) {
  return apiRequest('/users/me/generation-presets', { method: 'POST', body: payload });
}

export function deleteGenerationPreset(id) {
  return apiRequest(`/users/me/generation-presets/${id}`, { method: 'DELETE' });
}
