export const AUTH_FAILURE_EVENT = 'qbank:auth-failure';

function errorMessage(payload) {
  return String(payload?.detail || payload?.message || '').trim();
}

export function authFailureFor(status, payload) {
  if (status === 401) {
    return {
      status,
      message: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
    };
  }
  if (status !== 403) return null;

  const message = errorMessage(payload);
  if (!/(khóa|inactive|disabled)/i.test(message)) return null;
  return {
    status,
    message: message || 'Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.',
  };
}

export function notifyAuthFailure(status, payload) {
  const detail = authFailureFor(status, payload);
  if (!detail || typeof window === 'undefined') return detail;
  window.dispatchEvent(new CustomEvent(AUTH_FAILURE_EVENT, { detail }));
  return detail;
}
