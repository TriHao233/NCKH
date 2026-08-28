import { API_BASE_URL, apiFetch, authHeaders, parseError } from './client';

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

export async function streamGenerateStatus(jobId, options = {}) {
  const {
    signal,
    timeoutMs = 20 * 60 * 1000,
    terminal = ['completed', 'failed'],
    onUpdate,
  } = options;
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);
  signal?.addEventListener('abort', abortFromCaller, { once: true });
  const timeout = setTimeout(() => controller.abort('timeout'), timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}/generate/status/${jobId}/events`, {
      headers: { ...(await authHeaders()), Accept: 'text/event-stream' },
      signal: controller.signal,
    });
    if (!response.ok) await parseError(response);
    if (!response.body) throw new Error('Trình duyệt không hỗ trợ đọc luồng tiến độ');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let latest = null;

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n');
      const frames = buffer.split('\n\n');
      buffer = frames.pop() || '';

      for (const frame of frames) {
        const data = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n');
        if (!data) continue;
        latest = JSON.parse(data);
        onUpdate?.(latest);
        if (terminal.includes(latest.status)) return latest;
      }
      if (done) break;
    }
    throw new Error('Luồng tiến độ kết thúc trước khi job hoàn tất');
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Theo dõi job đã bị hủy', 'AbortError');
    if (controller.signal.aborted && controller.signal.reason === 'timeout') {
      const timeoutError = new Error('Hết thời gian chờ xử lý');
      timeoutError.name = 'TimeoutError';
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
