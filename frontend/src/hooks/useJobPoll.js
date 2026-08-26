const sleep = (ms, signal) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (!signal) return;

    if (signal.aborted) {
      clearTimeout(timer);
      reject(new DOMException('Polling aborted', 'AbortError'));
      return;
    }

    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Polling aborted', 'AbortError'));
      },
      { once: true },
    );
  });

export async function pollJob(fetchStatus, jobId, options = {}) {
  const {
    intervalMs = 2000,
    maxIntervalMs = 15000,
    backoffFactor = 1.5,
    jitterRatio = 0.2,
    terminal = ['completed', 'failed'],
    signal,
    timeoutMs = 600000,
    onUpdate,
  } = options;

  const startedAt = Date.now();
  let currentIntervalMs = intervalMs;

  while (true) {
    if (signal?.aborted) {
      throw new DOMException('Polling aborted', 'AbortError');
    }

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('Hết thời gian chờ xử lý');
    }

    const status = await fetchStatus(jobId, { signal });
    onUpdate?.(status);

    if (terminal.includes(status.status)) {
      return status;
    }

    const jitter = currentIntervalMs * jitterRatio * (Math.random() * 2 - 1);
    await sleep(Math.max(250, Math.round(currentIntervalMs + jitter)), signal);
    currentIntervalMs = Math.min(maxIntervalMs, currentIntervalMs * backoffFactor);
  }
}
