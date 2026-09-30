export function renewIntervalMs(timeoutMinutes) {
  return Math.max(60_000, Math.floor(timeoutMinutes * 60_000 / 3));
}
export function shouldRenewLock({ question, userId, now, lastActivityAt, timeoutMinutes, visible }) {
  const assignment = question?.review_assignment;
  const duration = timeoutMinutes * 60_000;
  const expires = Date.parse(assignment?.lock_expires_at);
  return Boolean(userId && question?.review_status === 'PENDING'
    && assignment?.status === 'IN_REVIEW'
    && String(assignment.reviewer_user_id) === String(userId)
    && visible && now - lastActivityAt <= duration
    && Number.isFinite(expires) && expires - now <= duration / 3);
}
