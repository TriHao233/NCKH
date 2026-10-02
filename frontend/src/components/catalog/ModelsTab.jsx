import React, { useMemo, useState } from 'react';
import { checkAiModelHealth, saveAiModel, setAiModelActive, updateAiModel } from '../../api/catalog';
import CatalogModal from './CatalogModal';

const CAPABILITIES = [
  { id: 'QUESTION_GENERATION', label: 'Sinh câu hỏi' },
  { id: 'QUESTION_EVALUATION', label: 'Đánh giá câu hỏi' },
];
const RUNTIME_LABEL = { OLLAMA: 'Ollama', GEMINI: 'Gemini' };
// Ô để trống nghĩa là dùng giá trị mặc định của máy chủ.
const CONFIG_FIELDS = ['timeout_seconds', 'temperature', 'num_predict', 'max_output_tokens', 'endpoint'];
const EMPTY_MODEL_FORM = {
  isNew: true,
  model_code: '',
  model_name: '',
  display_name: '',
  description: '',
  runtime: 'OLLAMA',
  kind: 'CHAT',
  revision: '',
  capabilities: ['QUESTION_GENERATION'],
  priority: 10,
  is_active: true,
  baseConfig: {},
  config: { timeout_seconds: '', temperature: '', num_predict: '', max_output_tokens: '', endpoint: '' },
};

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('vi-VN');
}

function modelToForm(model) {
  const config = model.config || {};
  return {
    isNew: false,
    model_code: model.model_code || '',
    model_name: model.model_name || '',
    display_name: model.display_name || model.model_name || '',
    description: model.description || '',
    runtime: model.runtime || 'OLLAMA',
    kind: model.kind || 'CHAT',
    revision: model.revision || '',
    capabilities: model.capabilities || [],
    priority: model.priority ?? 10,
    is_active: model.is_active !== false,
    baseConfig: config,
    config: Object.fromEntries(CONFIG_FIELDS.map((field) => [field, config[field] ?? ''])),
  };
}

function formToPayload(form) {
  const numberFields = form.runtime === 'GEMINI'
    ? ['timeout_seconds', 'temperature', 'max_output_tokens']
    : ['timeout_seconds', 'temperature', 'num_predict'];
  // Giữ các thiết lập khác của mô hình (ví dụ think, num_ctx) mà biểu mẫu không hiển thị.
  const config = Object.fromEntries(Object.entries(form.baseConfig).filter(([key]) => !CONFIG_FIELDS.includes(key)));
  numberFields.forEach((field) => {
    if (String(form.config[field]).trim() !== '') config[field] = Number(form.config[field]);
  });
  if (form.runtime === 'OLLAMA' && String(form.config.endpoint).trim()) config.endpoint = String(form.config.endpoint).trim();
  return {
    model_code: form.model_code,
    model_name: form.model_name,
    display_name: form.display_name,
    description: form.description,
    runtime: form.runtime,
    kind: form.kind,
    revision: form.revision || (form.runtime === 'OLLAMA' ? 'local' : 'remote'),
    capabilities: form.capabilities,
    priority: Number(form.priority) || 0,
    is_local: form.runtime === 'OLLAMA',
    is_active: form.is_active,
    config,
  };
}

function healthSummary(health) {
  if (!health) return { tone: 'muted', text: 'Chưa kiểm tra kết nối' };
  const checkedAt = formatDateTime(health.checked_at);
  if (health.status === 'OK') {
    return { tone: 'ok', text: `Hoạt động tốt · ${health.latency_ms || 0} ms${checkedAt ? ` · ${checkedAt}` : ''}` };
  }
  return { tone: 'warn', text: `Chưa sẵn sàng${health.error ? `: ${health.error}` : ''}${checkedAt ? ` · ${checkedAt}` : ''}` };
}

function ModelsTab({ models, runtimeConfig, saving, run, notify, reload }) {
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState('');
  const [checkingCode, setCheckingCode] = useState('');

  const defaults = {
    QUESTION_GENERATION: runtimeConfig.generation_model_provider,
    QUESTION_EVALUATION: runtimeConfig.evaluation_model_provider,
  };
  const sorted = useMemo(() => [...models].sort((left, right) => (
    Number(left.is_active === false) - Number(right.is_active === false)
    || Number(left.factory_status?.supported === false) - Number(right.factory_status?.supported === false)
    || (left.priority ?? 0) - (right.priority ?? 0)
  )), [models]);
  const modelName = (code) => {
    const model = models.find((item) => item.model_code === code);
    return model ? (model.display_name || model.model_name) : code;
  };
  const defaultWarnings = CAPABILITIES.map((capability) => {
    const code = defaults[capability.id];
    const model = models.find((item) => item.model_code === code);
    if (!code) return '';
    if (!model) return `Mô hình mặc định để ${capability.label.toLowerCase()} (${code}) chưa có trong danh sách.`;
    if (model.is_active === false) return `Mô hình mặc định để ${capability.label.toLowerCase()} (${modelName(code)}) đang bị khóa.`;
    return '';
  }).filter(Boolean);

  const openForm = (next) => {
    setFormError('');
    setForm(next);
  };
  const setField = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const setConfig = (field, value) => setForm((current) => ({ ...current, config: { ...current.config, [field]: value } }));
  const toggleCapability = (capability) => setForm((current) => ({
    ...current,
    capabilities: current.capabilities.includes(capability)
      ? current.capabilities.filter((item) => item !== capability)
      : [...current.capabilities, capability],
  }));

  const handleSave = async (event) => {
    event.preventDefault();
    setFormError('');
    if (form.capabilities.length === 0) {
      setFormError('Hãy chọn ít nhất một mục "Dùng cho".');
      return;
    }
    const payload = formToPayload(form);
    const outcome = await run(
      () => (form.isNew ? saveAiModel(payload) : updateAiModel(form.model_code, payload)),
      form.isNew ? 'Đã thêm mô hình.' : 'Đã lưu mô hình.',
      { quiet: true },
    );
    if (outcome.ok) setForm(null);
    else setFormError(outcome.error?.message || 'Lưu mô hình thất bại');
  };

  const toggleActive = (model) => {
    const lock = model.is_active !== false;
    if (lock) {
      const usedAsDefault = CAPABILITIES.filter((capability) => defaults[capability.id] === model.model_code)
        .map((capability) => capability.label.toLowerCase());
      const warning = usedAsDefault.length
        ? ` Đây đang là mô hình mặc định để ${usedAsDefault.join(' và ')}.`
        : '';
      if (!window.confirm(`Tạm khóa mô hình "${model.display_name || model.model_name}"?${warning} Người dùng sẽ không chọn được mô hình này nữa.`)) return;
    }
    run(
      () => setAiModelActive({ model_code: model.model_code, is_active: !lock }),
      lock ? 'Đã tạm khóa mô hình.' : 'Đã kích hoạt mô hình.',
    );
  };

  const handleCheck = async (model) => {
    setCheckingCode(model.model_code);
    try {
      const result = await checkAiModelHealth({ model_code: model.model_code, timeout_seconds: 30 });
      await reload();
      const name = model.display_name || model.model_name;
      if (result.status === 'OK') notify('success', `${name} hoạt động tốt (${result.latency_ms || 0} ms).`);
      else notify('error', `${name} chưa sẵn sàng${result.error ? `: ${result.error}` : '.'}`);
    } catch (err) {
      notify('error', err.message || 'Kiểm tra mô hình thất bại');
    } finally {
      setCheckingCode('');
    }
  };

  return (
    <div className="catalog-card">
      <div className="catalog-card-title-row">
        <div>
          <h2>Mô hình AI</h2>
          <p className="catalog-card-note">Danh sách mô hình mà giảng viên và người duyệt có thể chọn.</p>
        </div>
        <button type="button" onClick={() => openForm(EMPTY_MODEL_FORM)} disabled={saving}>Thêm mô hình</button>
      </div>

      <div className="catalog-defaults">
        {CAPABILITIES.map((capability) => (
          <div key={capability.id}>
            <small>Mặc định để {capability.label.toLowerCase()}</small>
            <b>{defaults[capability.id] ? modelName(defaults[capability.id]) : '--'}</b>
          </div>
        ))}
        <p>Mô hình mặc định do cấu hình máy chủ quy định, không đổi được tại đây.</p>
      </div>
      {defaultWarnings.map((warning) => <p className="catalog-banner" key={warning}>{warning}</p>)}

      <div className="catalog-list">
        {sorted.map((model) => {
          const health = healthSummary(model.last_health_check);
          const supported = model.factory_status?.supported !== false;
          return (
            <article className={`catalog-list-item ${model.is_active === false ? 'inactive' : ''}`} key={model.model_code}>
              <div>
                <b>
                  {model.display_name || model.model_name}
                  {(model.capabilities || []).map((capability) => (
                    <em className="catalog-badge" key={capability}>
                      {CAPABILITIES.find((item) => item.id === capability)?.label || capability}
                    </em>
                  ))}
                  {CAPABILITIES.filter((capability) => defaults[capability.id] === model.model_code).map((capability) => (
                    <em className="catalog-badge catalog-badge--default" key={capability.id}>Mặc định {capability.label.toLowerCase()}</em>
                  ))}
                  {model.is_active === false && <em className="catalog-badge catalog-badge--locked">Đã khóa</em>}
                  {!supported && <em className="catalog-badge catalog-badge--locked">Không còn hỗ trợ</em>}
                </b>
                <span>{model.model_name} · {RUNTIME_LABEL[model.runtime] || model.runtime} · mã {model.model_code}</span>
                {model.description && <span>{model.description}</span>}
                {supported
                  ? <span className={`catalog-health catalog-health--${health.tone}`}>{health.text}</span>
                  : <span className="catalog-health catalog-health--warn">{model.factory_status?.error || 'Hệ thống không chạy được mô hình này.'}</span>}
              </div>
              <div className="catalog-item-actions">
                <button type="button" className="catalog-ghost-button" onClick={() => handleCheck(model)} disabled={saving || !supported || checkingCode === model.model_code}>
                  {checkingCode === model.model_code ? 'Đang kiểm tra...' : 'Kiểm tra'}
                </button>
                <button type="button" className="catalog-ghost-button" onClick={() => openForm(modelToForm(model))} disabled={saving}>Sửa</button>
                <button type="button" className="catalog-ghost-button" onClick={() => toggleActive(model)} disabled={saving}>
                  {model.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                </button>
              </div>
            </article>
          );
        })}
        {sorted.length === 0 && <p className="catalog-empty-note">Chưa có mô hình nào.</p>}
      </div>

      {form && (
        <CatalogModal title={form.isNew ? 'Thêm mô hình' : `Sửa mô hình ${form.display_name || form.model_code}`} onClose={() => setForm(null)}>
          <form className="catalog-form" onSubmit={handleSave}>
            <label className="catalog-field">
              <span>Tên hiển thị</span>
              <input required maxLength={160} placeholder="Ví dụ: Qwen3 (8B)" value={form.display_name} onChange={(event) => setField('display_name', event.target.value)} />
            </label>
            <div className="catalog-columns">
              <label className="catalog-field">
                <span>Mã cấu hình</span>
                <input required maxLength={80} placeholder="Ví dụ: qwen3-8b" value={form.model_code} disabled={!form.isNew} onChange={(event) => setField('model_code', event.target.value)} />
                {!form.isNew && <small>Mã không đổi được sau khi tạo.</small>}
              </label>
              <label className="catalog-field">
                <span>Nền tảng</span>
                <select value={form.runtime} onChange={(event) => setField('runtime', event.target.value)}>
                  <option value="OLLAMA">Ollama</option>
                  <option value="GEMINI">Gemini</option>
                </select>
              </label>
            </div>
            <label className="catalog-field">
              <span>Tên model trên nền tảng</span>
              <input required maxLength={160} placeholder="Ví dụ: qwen3:8b" value={form.model_name} onChange={(event) => setField('model_name', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Mô tả ngắn</span>
              <input maxLength={300} placeholder="Người dùng nên chọn mô hình này khi nào?" value={form.description} onChange={(event) => setField('description', event.target.value)} />
            </label>
            <div className="catalog-field">
              <span>Dùng cho</span>
              <div className="catalog-columns">
                {CAPABILITIES.map((capability) => (
                  <label className="catalog-check" key={capability.id}>
                    <input type="checkbox" checked={form.capabilities.includes(capability.id)} onChange={() => toggleCapability(capability.id)} />
                    {capability.label}
                  </label>
                ))}
              </div>
            </div>
            <label className="catalog-field">
              <span>Thứ tự hiển thị</span>
              <input type="number" min="0" value={form.priority} onChange={(event) => setField('priority', event.target.value)} />
              <small>Số nhỏ hơn hiện trước trong danh sách chọn.</small>
            </label>
            <details className="catalog-model-advanced">
              <summary>Cài đặt nâng cao (để trống để dùng mặc định của máy chủ)</summary>
              <div className="catalog-columns">
                <label className="catalog-field">
                  <span>Thời gian chờ (giây)</span>
                  <input type="number" min="1" max="1800" value={form.config.timeout_seconds} onChange={(event) => setConfig('timeout_seconds', event.target.value)} />
                </label>
                <label className="catalog-field">
                  <span>Độ sáng tạo (0 đến 2)</span>
                  <input type="number" min="0" max="2" step="0.1" value={form.config.temperature} onChange={(event) => setConfig('temperature', event.target.value)} />
                </label>
              </div>
              {form.runtime === 'OLLAMA' ? (
                <>
                  <label className="catalog-field">
                    <span>Số token tối đa</span>
                    <input type="number" min="1" max="32768" value={form.config.num_predict} onChange={(event) => setConfig('num_predict', event.target.value)} />
                  </label>
                  <label className="catalog-field">
                    <span>Địa chỉ Ollama</span>
                    <input placeholder="Để trống để dùng địa chỉ của máy chủ" value={form.config.endpoint} onChange={(event) => setConfig('endpoint', event.target.value)} />
                    <small>Chỉ nhận đúng địa chỉ Ollama mà máy chủ đã cấu hình.</small>
                  </label>
                </>
              ) : (
                <label className="catalog-field">
                  <span>Số token tối đa</span>
                  <input type="number" min="1" max="65536" value={form.config.max_output_tokens} onChange={(event) => setConfig('max_output_tokens', event.target.value)} />
                </label>
              )}
            </details>
            <label className="catalog-check">
              <input type="checkbox" checked={form.is_active} onChange={(event) => setField('is_active', event.target.checked)} />
              Đang dùng
            </label>
            {formError && <p className="catalog-form-error" role="alert">{formError}</p>}
            <div className="catalog-form-actions">
              <button type="button" className="catalog-ghost-button" onClick={() => setForm(null)} disabled={saving}>Hủy</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu mô hình'}</button>
            </div>
          </form>
        </CatalogModal>
      )}
    </div>
  );
}

export default ModelsTab;
