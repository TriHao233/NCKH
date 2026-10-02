import React, { useMemo, useState } from 'react';
import { activateEvaluationPolicy, saveEvaluationPolicy } from '../../api/catalog';
import {
  THRESHOLD_FIELDS,
  describePolicyChanges,
  formToPayload,
  formatThreshold,
  policyToForm,
  validatePolicyForm,
  weightKeys,
  weightLabel,
  weightToPercent,
  weightTotal,
} from '../../utils/evaluationPolicy';
import CatalogModal from './CatalogModal';

const DEFAULT_POLICY = {
  policy_name: 'Default question quality policy',
  weights: { faithfulness: 0.35, contextual_relevancy: 0.2, answer_relevancy: 0.15, bloom_alignment: 0.15, clo_alignment: 0.15 },
  thresholds: { yellow_min: 0.5, pass_min: 0.7, green_min: 0.75 },
};

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('vi-VN');
}

function PolicyTab({ policies, fallbackPolicy, saving, run }) {
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState('');

  const sorted = useMemo(() => [...policies].sort((left, right) => (
    String(left.policy_name).localeCompare(String(right.policy_name)) || right.version - left.version
  )), [policies]);
  const active = sorted.find((policy) => policy.is_active) || null;
  const previousOf = (policy) => sorted.find((item) => (
    item.policy_name === policy.policy_name && item.version === policy.version - 1
  ));

  const openForm = (policy) => {
    setFormError('');
    setForm(policyToForm(policy));
  };
  const setWeight = (key, value) => setForm((current) => ({ ...current, weights: { ...current.weights, [key]: value } }));
  const setThreshold = (key, value) => setForm((current) => ({ ...current, thresholds: { ...current.thresholds, [key]: value } }));

  const handleSave = async (event) => {
    event.preventDefault();
    setFormError('');
    const problem = validatePolicyForm(form);
    if (problem) {
      setFormError(problem);
      return;
    }
    if (!window.confirm('Lưu thành phiên bản mới và áp dụng ngay cho các lượt AI chấm tiếp theo? Những câu đã chấm giữ nguyên kết quả.')) return;
    const outcome = await run(
      () => saveEvaluationPolicy({ ...formToPayload(form), create_new_version: true, is_active: true }),
      'Đã lưu và áp dụng bộ tiêu chí mới.',
      { quiet: true },
    );
    if (outcome.ok) setForm(null);
    else setFormError(outcome.error?.message || 'Lưu bộ tiêu chí thất bại');
  };

  const handleActivate = (policy) => {
    if (!window.confirm(`Chuyển sang dùng phiên bản ${policy.version}? Các lượt AI chấm tiếp theo sẽ theo phiên bản này.`)) return;
    run(
      () => activateEvaluationPolicy({ policy_name: policy.policy_name, version: policy.version, is_active: true }),
      `Đã chuyển sang dùng phiên bản ${policy.version}.`,
    );
  };

  const total = form ? weightTotal(form) : 0;
  const shown = active || (fallbackPolicy?.weights ? fallbackPolicy : DEFAULT_POLICY);

  return (
    <div className="catalog-card">
      <div className="catalog-card-title-row">
        <div>
          <h2>Tiêu chí đánh giá</h2>
          <p className="catalog-card-note">AI chấm từng tiêu chí rồi cộng theo trọng số thành tổng điểm; các ngưỡng quyết định kết luận và màu chất lượng.</p>
        </div>
        <button type="button" onClick={() => openForm(shown)} disabled={saving}>Sửa tiêu chí</button>
      </div>

      <section className="policy-current">
        <div className="catalog-section-head">
          <h4>
            {active
              ? `Đang áp dụng: ${active.policy_name} · phiên bản ${active.version}`
              : 'Chưa có bộ tiêu chí nào được bật; hệ thống dùng giá trị mặc định dưới đây'}
          </h4>
          {active?.created_at && <small>Tạo lúc {formatDateTime(active.created_at)}</small>}
        </div>
        <div className="catalog-columns">
          <div>
            <h5>Trọng số</h5>
            {weightKeys(shown.weights).map((key) => (
              <div className="policy-weight" key={key}>
                <span>{weightLabel(key)}</span>
                <div className="policy-weight-track"><i style={{ width: `${Math.min(100, weightToPercent(shown.weights[key]))}%` }} /></div>
                <b>{weightToPercent(shown.weights[key])}%</b>
              </div>
            ))}
          </div>
          <div>
            <h5>Ngưỡng điểm (thang 0 đến 1)</h5>
            {THRESHOLD_FIELDS.map((field) => (
              <div className="policy-threshold" key={field.key}>
                <span>{field.label}<small>{field.hint}</small></span>
                <b>{formatThreshold(shown.thresholds?.[field.key])}</b>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="catalog-section">
        <div className="catalog-section-head">
          <h4>Lịch sử phiên bản ({sorted.length})</h4>
        </div>
        <div className="catalog-list">
          {sorted.map((policy) => {
            const previous = previousOf(policy);
            const changes = describePolicyChanges(previous, policy);
            return (
              <article className="catalog-list-item" key={policy._id || `${policy.policy_name}-${policy.version}`}>
                <div>
                  <b>
                    Phiên bản {policy.version}
                    {policy.is_active && <em className="catalog-badge catalog-badge--default">Đang áp dụng</em>}
                  </b>
                  <span>{policy.policy_name}{policy.created_at ? ` · ${formatDateTime(policy.created_at)}` : ''}</span>
                  <span>
                    {!previous
                      ? 'Bản đầu tiên'
                      : changes.length ? `Thay đổi: ${changes.join('; ')}` : 'Không khác bản trước'}
                  </span>
                </div>
                <div className="catalog-item-actions">
                  <button type="button" className="catalog-ghost-button" onClick={() => openForm(policy)} disabled={saving}>Sửa từ bản này</button>
                  {!policy.is_active && (
                    <button type="button" className="catalog-ghost-button" onClick={() => handleActivate(policy)} disabled={saving}>Dùng phiên bản này</button>
                  )}
                </div>
              </article>
            );
          })}
          {sorted.length === 0 && <p className="catalog-empty-note">Chưa có phiên bản nào được lưu.</p>}
        </div>
      </section>

      {form && (
        <CatalogModal title="Sửa tiêu chí đánh giá" onClose={() => setForm(null)} wide>
          <form className="catalog-form" onSubmit={handleSave}>
            <label className="catalog-field">
              <span>Tên bộ tiêu chí</span>
              <input required maxLength={160} value={form.policy_name} onChange={(event) => setForm({ ...form, policy_name: event.target.value })} />
            </label>
            <div className="catalog-columns">
              <fieldset className="policy-fieldset">
                <legend>Trọng số (%)</legend>
                {Object.keys(form.weights).map((key) => (
                  <label className="policy-input-row" key={key}>
                    <span>{weightLabel(key)}</span>
                    <input type="number" min="0" max="100" step="any" required value={form.weights[key]} onChange={(event) => setWeight(key, event.target.value)} />
                  </label>
                ))}
                <p className={`policy-total ${Math.abs(total - 100) > 0.01 ? 'policy-total--bad' : ''}`}>
                  Tổng: {total}% {Math.abs(total - 100) > 0.01 ? '(cần bằng 100%)' : ''}
                </p>
              </fieldset>
              <fieldset className="policy-fieldset">
                <legend>Ngưỡng điểm (0 đến 1)</legend>
                {THRESHOLD_FIELDS.map((field) => (
                  <label className="policy-input-row" key={field.key}>
                    <span>{field.label}<small>{field.hint}</small></span>
                    <input type="number" min="0" max="1" step="0.01" required value={form.thresholds[field.key]} onChange={(event) => setThreshold(field.key, event.target.value)} />
                  </label>
                ))}
              </fieldset>
            </div>
            {formError && <p className="catalog-form-error" role="alert">{formError}</p>}
            <div className="catalog-form-actions">
              <button type="button" className="catalog-ghost-button" onClick={() => setForm(null)} disabled={saving}>Hủy</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu và áp dụng'}</button>
            </div>
          </form>
        </CatalogModal>
      )}
    </div>
  );
}

export default PolicyTab;
