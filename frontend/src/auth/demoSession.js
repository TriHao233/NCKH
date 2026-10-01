const DEMO_SESSION_STORAGE_KEY = 'qbank_demo_session';

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

export function demoAuthHeaders() {
  const session = readDemoSession();
  return session ? { Authorization: `Bearer ${session.token}` } : null;
}
