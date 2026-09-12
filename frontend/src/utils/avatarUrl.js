export function normalizeAvatarUrl(value) {
  const avatar = (value || '').trim();
  if (!avatar) return '';
  if (avatar.startsWith('/api/')) return avatar;
  try {
    const url = new URL(avatar);
    if (url.pathname.startsWith('/api/')) {
      return `${url.pathname}${url.search}${url.hash}`;
    }
  } catch {
    // Keep the original value so callers can validate or display a useful error.
  }
  return avatar;
}

export function buildFallbackAvatar(name) {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name || 'U')}&background=0c78d4&color=fff`;
}
