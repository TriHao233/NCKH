import React, { useEffect, useState } from 'react';
import { getReviewPolicy, updateReviewPolicy } from '../../api/questions';
import { percentToScore, scoreToPercent } from '../../utils/reviewPolicy';

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('vi-VN');
}

function draftFrom(policy) {
  return {
    secondary_on_override: Boolean(policy.secondary_on_override),
    scorePercent: scoreToPercent(policy.secondary_below_score),
    secondary_subject_ids: policy.secondary_subject_ids || [],
  };
}

function ReviewPolicyTab({ subjects, notify }) {
  const [policy, setPolicy] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    getReviewPolicy()
      .then((result) => {
        if (!active) return;
        setPolicy(result);
        setDraft(draftFrom(result));
      })
      .catch((err) => { if (active) setLoadError(err.message || 'Không tải được chính sách kiểm duyệt'); });
    return () => { active = false; };
  }, []);

  const toggleSubject = (subjectId) => setDraft((current) => ({
    ...current,
    secondary_subject_ids: current.secondary_subject_ids.includes(subjectId)
      ? current.secondary_subject_ids.filter((id) => id !== subjectId)
      : [...current.secondary_subject_ids, subjectId],
  }));

  const handleSave = async (event) => {
    event.preventDefault();
    setFormError('');
    let belowScore;
    try {
      belowScore = percentToScore(draft.scorePercent);
    } catch (err) {
      setFormError(err.message);
      return;
    }
    setSaving(true);
    try {
      const saved = await updateReviewPolicy({
        secondary_on_override: draft.secondary_on_override,
        secondary_below_score: belowScore,
        secondary_subject_ids: draft.secondary_subject_ids,
      });
      setPolicy(saved);
      setDraft(draftFrom(saved));
      notify('success', 'Đã lưu chính sách duyệt lần 2.');
    } catch (err) {
      setFormError(err.message || 'Lưu chính sách thất bại');
    } finally {
      setSaving(false);
    }
  };

  const dirty = policy && draft && JSON.stringify(draft) !== JSON.stringify(draftFrom(policy));

  return (
    <div className="catalog-card">
      <div className="catalog-card-title-row">
        <div>
          <h2>Chính sách duyệt lần 2</h2>
          <p className="catalog-card-note">Khi nào một câu hỏi đã được duyệt vẫn cần thêm người duyệt thứ hai xác nhận.</p>
        </div>
      </div>

      {loadError && <p className="catalog-form-error" role="alert">{loadError}</p>}
      {!draft && !loadError && <p className="catalog-empty-note">Đang tải chính sách...</p>}

      {draft && (
        <form className="catalog-form" onSubmit={handleSave}>
          <label className="catalog-check">
            <input
              type="checkbox"
              checked={draft.secondary_on_override}
              onChange={(event) => setDraft({ ...draft, secondary_on_override: event.target.checked })}
            />
            Bắt duyệt lần 2 khi người duyệt vẫn duyệt dù AI đề xuất xem lại
          </label>
          <label className="catalog-field">
            <span>Bắt duyệt lần 2 khi điểm AI dưới (%)</span>
            <input
              type="number"
              min="0"
              max="100"
              step="any"
              placeholder="Để trống để tắt"
              value={draft.scorePercent}
              onChange={(event) => setDraft({ ...draft, scorePercent: event.target.value })}
            />
            <small>Ví dụ nhập 60: câu có tổng điểm AI dưới 0.60 mà vẫn được duyệt sẽ cần duyệt lần 2.</small>
          </label>
          <div className="catalog-field">
            <span>Luôn duyệt lần 2 với các học phần</span>
            {subjects.filter((subject) => subject.is_active !== false || draft.secondary_subject_ids.includes(subject.id)).map((subject) => (
              <label className="catalog-check" key={subject.id}>
                <input type="checkbox" checked={draft.secondary_subject_ids.includes(subject.id)} onChange={() => toggleSubject(subject.id)} />
                {subject.subject_code} — {subject.subject_name}
              </label>
            ))}
            {subjects.length === 0 && <small>Chưa có học phần nào.</small>}
          </div>
          {policy && (
            <p className="catalog-card-note">
              Thời gian giữ câu khi đang duyệt: {policy.lock_timeout_minutes} phút · Hạn nhận câu được giao: {policy.assignment_timeout_hours} giờ
              (hai giá trị này do cấu hình máy chủ quy định).
              {policy.updated_at ? ` Cập nhật lần cuối: ${formatDateTime(policy.updated_at)}.` : ''}
            </p>
          )}
          {formError && <p className="catalog-form-error" role="alert">{formError}</p>}
          <div className="catalog-form-actions">
            <button type="button" className="catalog-ghost-button" onClick={() => { setDraft(draftFrom(policy)); setFormError(''); }} disabled={saving || !dirty}>Bỏ thay đổi</button>
            <button type="submit" disabled={saving || !dirty}>{saving ? 'Đang lưu...' : 'Lưu chính sách'}</button>
          </div>
        </form>
      )}
    </div>
  );
}

export default ReviewPolicyTab;
