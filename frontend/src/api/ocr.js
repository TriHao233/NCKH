import { API_BASE_URL, apiFetch, authHeaders, parseError } from './client';

export async function uploadOcrPdf(file) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE_URL}/api/v1/ocr/upload`, {
    method: 'POST',
    headers: await authHeaders(),
    body: form,
  });
  if (!response.ok) {
    await parseError(response);
  }
  return response.json();
}

export function getOcrStatus(jobId, options = {}) {
  return apiFetch(`/api/v1/ocr/status/${jobId}`, options);
}
