import { apiRequest } from '../services/apiClient';

export function listAdminAuditLogs({
  page = 1,
  pageSize = 25,
  actorUserId,
  entityType,
  entityId,
  action,
  dateFrom,
  dateTo,
  search,
} = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  if (actorUserId) params.set('actor_user_id', actorUserId);
  if (entityType && entityType !== 'all') params.set('entity_type', entityType);
  if (entityId) params.set('entity_id', entityId);
  if (action && action !== 'all') params.set('action', action);
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo) params.set('date_to', dateTo);
  if (search) params.set('search', search);
  return apiRequest(`/admin/audit-logs?${params.toString()}`);
}
