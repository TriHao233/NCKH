export function renewIntervalMs(timeoutMinutes) {
  return Math.max(60_000, Math.floor(timeoutMinutes * 60_000 / 3));
}

// Gia hạn khi khoá còn không quá 2/3 thời lượng. Ngưỡng phải lớn hơn chu kỳ kiểm tra (1/3):
// nếu bằng nhau thì cứ hai nhịp mới gia hạn một lần và lần đó rơi đúng lúc khoá vừa hết.
export function shouldRenewLock({ question, userId, now, lastActivityAt, timeoutMinutes, visible }) {
  const assignment = question?.review_assignment;
  const duration = timeoutMinutes * 60_000;
  const expires = Date.parse(assignment?.lock_expires_at);
  return Boolean(userId && question?.review_status === 'PENDING'
    && assignment?.status === 'IN_REVIEW'
    && String(assignment.reviewer_user_id) === String(userId)
    && visible && now - lastActivityAt <= duration
    && Number.isFinite(expires) && expires - now <= duration * 2 / 3);
}
