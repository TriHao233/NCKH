export function parseGenerateStatusSseFrame(frame) {
  const lines = frame.split('\n');
  const eventName = lines
    .find((line) => line.startsWith('event:'))
    ?.slice(6)
    .trim();
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');

  if (!data) return null;
  if (eventName === 'error') {
    throw new Error(data);
  }

  const payload = JSON.parse(data);
  if (!payload || typeof payload.status !== 'string') {
    throw new Error('Luồng tiến độ trả về dữ liệu không hợp lệ');
  }
  return payload;
}
