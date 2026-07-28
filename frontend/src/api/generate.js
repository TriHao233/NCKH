import { apiFetch } from './client';

export function enqueueGenerateQuestions(payload) {
  return apiFetch('/generate/questions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getGenerateStatus(jobId, options = {}) {
  return apiFetch(`/generate/status/${jobId}`, options);
}
