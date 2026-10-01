import { apiRequest } from '../services/apiClient';

export function createContactRequest({ category, title, content }) {
  return apiRequest('/contact/requests', {
    method: 'POST',
    body: { category, title, content },
  });
}

export function listContactRequests({
  page = 1,
  pageSize = 20,
  status,
  category,
  search,
  scope = 'mine',
} = {}) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);
  params.set('scope', scope);
  if (status) params.set('status', status);
  if (category) params.set('category', category);
  if (search) params.set('search', search);
  return apiRequest(`/contact/requests?${params.toString()}`);
}

export function getContactRequest(id) {
  return apiRequest(`/contact/requests/${id}`);
}

export function editContactRequest(id, changes) {
  return apiRequest(`/contact/requests/${id}`, { method: 'PATCH', body: changes });
}

export function withdrawContactRequest(id) {
  return apiRequest(`/contact/requests/${id}/withdraw`, { method: 'POST' });
}

export function deleteContactRequest(id) {
  return apiRequest(`/contact/requests/${id}`, { method: 'DELETE' });
}

export function restoreContactRequest(id) {
  return apiRequest(`/contact/requests/${id}/restore`, { method: 'POST' });
}

export function replyContactRequest(id, message) {
  return apiRequest(`/contact/requests/${id}/messages`, {
    method: 'POST',
    body: { message },
  });
}

export function submitContactResponse(id, { status, message }) {
  return apiRequest(`/contact/requests/${id}/respond`, {
    method: 'POST',
    body: { status, message },
  });
}

export function updateContactStatus(id, statusValue) {
  return apiRequest(`/contact/requests/${id}/status`, {
    method: 'PATCH',
    body: { status: statusValue },
  });
}

export const CONTACT_CATEGORIES = [
  { value: 'REVIEW_REQUEST', label: 'Yêu cầu duyệt câu hỏi' },
  { value: 'BUG', label: 'Báo lỗi hệ thống' },
  { value: 'SUPPORT', label: 'Yêu cầu hỗ trợ' },
  { value: 'FEEDBACK', label: 'Góp ý / đề xuất' },
  { value: 'CONTENT_ISSUE', label: 'Báo sai sót nội dung câu hỏi' },
];

export const CONTACT_STATUSES = [
  { value: 'NEW', label: 'Mới' },
  { value: 'IN_PROGRESS', label: 'Đang xử lý' },
  { value: 'RESOLVED', label: 'Đã giải quyết' },
  { value: 'CLOSED', label: 'Đã đóng' },
  { value: 'WITHDRAWN', label: 'Đã thu hồi' },
];

export function labelForCategory(value) {
  return CONTACT_CATEGORIES.find((c) => c.value === value)?.label || value;
}

export function labelForStatus(value) {
  return CONTACT_STATUSES.find((s) => s.value === value)?.label || value;
}
