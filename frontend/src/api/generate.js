import { apiFetch } from './client';

export function enqueueGenerateQuestions(payload) {
  return apiFetch('/api/v1/generate/questions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getGenerateStatus(jobId, options = {}) {
  return apiFetch(`/api/v1/generate/status/${jobId}`, options);
}
