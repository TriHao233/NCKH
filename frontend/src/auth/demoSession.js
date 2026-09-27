const DEMO_SESSION_STORAGE_KEY = 'qbank_demo_session';
export const DEMO_SESSION_EXPIRED_EVENT = 'qbank:demo-session-expired';

export function readDemoSession() {
  try {
    const rawValue = globalThis.localStorage?.getItem(DEMO_SESSION_STORAGE_KEY);
    const parsed = rawValue ? JSON.parse(rawValue) : null;
    if (!parsed?.token || !parsed?.user) return null;
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
  if (readDemoSession()?.token !== expectedToken) return false;
  clearDemoSession();
  globalThis.localStorage?.removeItem('userInfo');
  globalThis.window?.dispatchEvent(new Event(DEMO_SESSION_EXPIRED_EVENT));
  return true;
}

export function demoAuthHeaders() {
  const session = readDemoSession();
  return session ? { Authorization: `Bearer ${session.token}` } : null;
}
