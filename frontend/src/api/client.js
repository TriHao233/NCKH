export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000';

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

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    await parseError(response);
  }
  return response.json();
}
