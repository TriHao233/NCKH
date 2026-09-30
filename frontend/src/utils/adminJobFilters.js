export const STATUS_OPTIONS = [
  { value: 'all', label: 'Tất cả trạng thái' },
  { value: 'active', label: 'Đang chờ / đang xử lý' },
  { value: 'retryable', label: 'Cần xử lý / có thể chạy lại' },
  { value: 'queued', label: 'Sinh câu hỏi: đang chờ' },
  { value: 'processing', label: 'Sinh câu hỏi: đang xử lý' },
  { value: 'failed', label: 'Sinh câu hỏi: thất bại' },
  { value: 'QUEUED', label: 'Tác vụ: đang chờ' },
  { value: 'PROCESSING', label: 'Tác vụ: đang xử lý' },
  { value: 'FAILED', label: 'Tác vụ: thất bại' },
  { value: 'ERROR', label: 'Tác vụ: lỗi' },
  { value: 'STALE', label: 'Tác vụ: cần chạy lại' },
  { value: 'BLOCKED', label: 'Tác vụ: thiếu bằng chứng' },
  { value: 'COMPLETED', label: 'Tác vụ: hoàn tất' },
  { value: 'CANCELLED', label: 'Tác vụ: đã hủy' },
];

export function parseJobFilters(search) {
  const params = new URLSearchParams(search);
  const kind = params.get('kind');
  const status = params.get('status');
  return { kind: ['all', 'generation', 'evaluation', 'document'].includes(kind) ? kind : 'all',
    status: STATUS_OPTIONS.some((item) => item.value === status) ? status : 'all',
    staleOnly: params.get('stale_only') === 'true', search: params.get('search') || '' };
}
