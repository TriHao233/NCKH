const DEMO_SESSION_STORAGE_KEY = 'qbank_demo_session';

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

export function demoAuthHeaders() {
  const session = readDemoSession();
  return session ? { Authorization: `Bearer ${session.token}` } : null;
}
