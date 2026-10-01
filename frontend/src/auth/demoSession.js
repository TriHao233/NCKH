const DEMO_SESSION_STORAGE_KEY = 'qbank_demo_session';
// Một sự kiện chung cho mọi kiểu phiên (demo và Firebase); AuthContext lắng nghe sự kiện này.
export const SESSION_EXPIRED_EVENT = 'qbank:session-expired';

export function readDemoSession() {
  try {
    const rawValue = globalThis.localStorage?.getItem(DEMO_SESSION_STORAGE_KEY);
    const parsed = rawValue ? JSON.parse(rawValue) : null;
    if (!parsed?.token || !parsed?.user) return null;
    const [prefix, payload] = parsed.token.split('.');
    if (prefix !== 'demo' || !payload) throw new Error('Invalid demo session');
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const claims = JSON.parse(globalThis.atob(base64));
    if (!Number.isFinite(claims.exp) || claims.exp <= Date.now() / 1000) {
      throw new Error('Expired demo session');
    }
    return parsed;
  } catch {
    globalThis.localStorage?.removeItem(DEMO_SESSION_STORAGE_KEY);
    return null;
  }
}

export function saveDemoSession(token, user) {
  globalThis.localStorage?.setItem(
    DEMO_SESSION_STORAGE_KEY,
    JSON.stringify({ token, user }),
  );
}

export function clearDemoSession() {
  globalThis.localStorage?.removeItem(DEMO_SESSION_STORAGE_KEY);
}

export function expireDemoSession(expectedToken) {
  if (!expectedToken || readDemoSession()?.token !== expectedToken) return false;
  clearDemoSession();
  globalThis.localStorage?.removeItem('userInfo');
  globalThis.dispatchEvent?.(new Event(SESSION_EXPIRED_EVENT));
  return true;
}

export function handleDemoSessionResponse(status, authorization) {
  if (status !== 401 || !authorization?.startsWith('Bearer demo.')) return false;
  return expireDemoSession(authorization.slice('Bearer '.length));
}

export function demoAuthHeaders() {
  const session = readDemoSession();
  return session ? { Authorization: `Bearer ${session.token}` } : null;
}
