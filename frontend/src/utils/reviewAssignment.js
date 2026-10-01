const REASONS = {
  NO_REVIEWERS: 'Chưa có người duyệt đang hoạt động',
  NO_SUBJECT_SPECIALIST: 'Không có người phụ trách học phần này',
  NO_ELIGIBLE_REVIEWER: 'Không ai đủ điều kiện (là tác giả, đang duyệt lần đầu, hoặc đã đủ tải)',
};
const FLAGS = {
  HIGH_OVERRIDE: 'Hay duyệt khác AI', HIGH_BULK: 'Duyệt hàng loạt nhiều',
  SLA_BREACHED: 'Có câu quá hạn', NO_SUBJECTS: 'Chưa gán học phần',
};
export function assignmentReasonLabel(reason) { return REASONS[reason] || reason; }
export function reviewerFlagLabel(flag) { return FLAGS[flag] || flag; }
