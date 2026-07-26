import { API_BASE_URL, apiFetch, authHeaders, parseError } from './client';

export async function uploadOcrPdf(file, { subjectId, chapterId } = {}) {
  const form = new FormData();
  form.append('file', file);
  if (subjectId) form.append('subject_id', subjectId);
  if (chapterId) form.append('chapter_id', chapterId);
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/upload`, {
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
