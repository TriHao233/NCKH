import { auth } from '../../firebase';

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function parseError(response) {
  let detail = `HTTP ${response.status}`;
  try {
    const body = await response.json();
    detail = body.detail || body.message || detail;
  } catch {
    /* ignore */
  }
  throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
}

export async function authHeaders() {
  await auth.authStateReady();
  const firebaseUser = auth.currentUser;
  if (!firebaseUser) {
    throw new Error('Bạn chưa đăng nhập');
  }
  return { Authorization: `Bearer ${await firebaseUser.getIdToken()}` };
}

export async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}), ...(await authHeaders()) };
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    await parseError(response);
  }
  return response.json();
}
