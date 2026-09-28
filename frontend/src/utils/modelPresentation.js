export function modelPresentation(model = {}) {
  const name = String(model.name || '').trim();
  const version = String(model.version || '').trim();
  const identity = `${name} ${version} ${model.code || ''}`.toLowerCase();
  const family = identity.includes('gemini') ? 'gemini' : identity.includes('qwen') ? 'qwen' : 'other';
  const readable = (value) => value
    .replace(/gemini[-\s]*/gi, 'Gemini ')
    .replace(/qwen\s*(\d)/gi, 'Qwen $1')
    .replace(/:(\d+(?:\.\d+)?)b\b/gi, ' ($1B)')
    .replace(/\b(\d+(?:\.\d+)?)b\b/gi, '$1B')
    .replace(/\bflash\b/gi, 'Flash')
    .replace(/\bpro\b/gi, 'Pro')
    .replace(/\bthinking\b/gi, 'Thinking')
    .replace(/-/g, ' ')
    .replace(/\s+/g, ' ').trim();
  const canonical = (value) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  const friendlyName = readable(name || version || model.code || 'Mô hình mặc định');
  const friendlyVersion = readable(version);
  const genericName = ['gemini', 'qwen'].includes(canonical(friendlyName));
  return {
    family,
    label: genericName && friendlyVersion ? friendlyVersion : friendlyName,
    detail: !genericName && friendlyVersion && canonical(friendlyName) !== canonical(friendlyVersion)
      ? friendlyVersion : '',
  };
}
