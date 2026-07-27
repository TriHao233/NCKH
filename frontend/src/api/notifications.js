import { apiRequest } from '../services/apiClient';

export function listNotifications({ page = 1, pageSize = 20, unreadOnly = false } = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (unreadOnly) params.set('unread_only', 'true');
  return apiRequest(`/notifications?${params.toString()}`);
}

export function getUnreadNotificationCount() {
  return apiRequest('/notifications/unread-count');
}

export function markNotificationRead(id) {
  return apiRequest(`/notifications/${id}/read`, { method: 'POST' });
}

export function markAllNotificationsRead() {
  return apiRequest('/notifications/read-all', { method: 'POST' });
}
