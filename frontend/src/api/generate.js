import { apiFetch } from './client';

export function enqueueGenerateQuestions(payload, idempotencyKey) {
  return apiFetch('/generate/questions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    body: JSON.stringify(payload),
  });
}

export function getGenerateStatus(jobId, options = {}) {
  return apiFetch(`/generate/status/${jobId}`, options);
}
