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
    terminal = ['completed', 'failed'],
    signal,
    timeoutMs = 600000,
    onUpdate,
  } = options;

  const startedAt = Date.now();

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

    await sleep(intervalMs, signal);
  }
}
