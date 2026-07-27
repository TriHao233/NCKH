import { apiRequest } from '../services/apiClient';

export function getAdminOverview() {
  return apiRequest('/admin/overview');
}
