import React, { useEffect, useMemo, useState } from 'react';
import { BLOOM_LEVELS, DIFFICULTIES, QUESTION_TYPES, questionTypeLabel } from '../../constants/generationEnums';
import {
  DEFAULT_OPTION_KEYS,
  MULTI_CHOICE_TYPES,
  SINGLE_CHOICE_TYPES,
  STRUCTURED_OPTION_TYPES,
  correctAnswerValues,
  entriesToOptions,
  joinCorrectValues,
  optionEntriesForQuestion,
  validateQuestionAnswer,
} from '../../utils/questionOptions';
import { questionTypeOf } from '../../utils/questionBankView';

const OPTION_KEYS = [...DEFAULT_OPTION_KEYS, 'E', 'F', 'G', 'H'];

function refId(value) {
  if (!value) return '';
  return typeof value === 'string' ? value : value.id || value._id || '';
}

function formFor(question) {
  if (!question) {
    return {
      subjectId: '',
      questionType: QUESTION_TYPES[0]?.backend || 'trac_nghiem',
      bloomLevel: '',
      difficulty: '',
      content: '',
      rawOptions: null,
      correctAnswer: '',
      explanation: '',
      cloIds: [],
      changeNote: '',
    };
  }
  return {
    subjectId: refId(question.classification?.subject?.id) || question.subject_id || '',
    questionType: questionTypeOf(question),
    bloomLevel: question.classification?.bloom?.level ? String(question.classification.bloom.level) : '',
    difficulty: question.classification?.difficulty || '',
    content: question.content || '',
    rawOptions: question.question_data?.options ?? null,
    correctAnswer: question.question_data?.correct_answer ?? '',
    explanation: question.question_data?.explanation ?? '',
    cloIds: (question.clos || []).map((clo) => refId(clo.id || clo)).filter(Boolean),
    changeNote: '',
  };
}

function QuestionEditorDialog({ question, subjects, saving, error, onSubmit, onClose }) {
  const isEdit = Boolean(question);
  const [form, setForm] = useState(() => formFor(question));
  const [formError, setFormError] = useState('');
  const original = useMemo(() => formFor(question), [question]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const setField = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const entries = optionEntriesForQuestion({ questionType: form.questionType, rawOptions: form.rawOptions });
  const structured = STRUCTURED_OPTION_TYPES.has(form.questionType);
  const canChangeOptionCount = structured && form.questionType !== 'dung_sai';
  const subject = subjects.find((item) => refId(item) === form.subjectId);
  const outcomes = (subject?.learning_outcomes || []).filter((clo) => clo.is_active !== false || form.cloIds.includes(refId(clo)));

  const setEntries = (nextEntries) => setField('rawOptions', entriesToOptions(nextEntries));
  const updateOption = (key, value) => setEntries(entries.map((entry) => (entry.key === key ? { ...entry, value } : entry)));
  const addOption = () => {
    const nextKey = OPTION_KEYS.find((key) => !entries.some((entry) => entry.key === key)) || String(entries.length + 1);
    setEntries([...entries, { key: nextKey, value: '' }]);
  };
  const removeOption = (key) => {
    const nextEntries = entries.filter((entry) => entry.key !== key);
    setForm((current) => ({
      ...current,
      rawOptions: entriesToOptions(nextEntries),
      correctAnswer: SINGLE_CHOICE_TYPES.has(current.questionType) || MULTI_CHOICE_TYPES.has(current.questionType)
        ? joinCorrectValues(correctAnswerValues(current.correctAnswer).filter((value) => value !== key), nextEntries)
        : current.correctAnswer,
    }));
  };
  const toggleCorrect = (key) => {
    const values = correctAnswerValues(form.correctAnswer);
    const next = values.includes(key) ? values.filter((value) => value !== key) : [...values, key];
    setField('correctAnswer', joinCorrectValues(next, entries));
  };
  const toggleClo = (cloId) => setField(
    'cloIds',
    form.cloIds.includes(cloId) ? form.cloIds.filter((value) => value !== cloId) : [...form.cloIds, cloId],
  );

  const handleSubmit = (event) => {
    event.preventDefault();
    setFormError('');
    if (!isEdit && !form.subjectId) {
      setFormError('Hãy chọn học phần cho câu hỏi.');
      return;
    }
    if (!form.content.trim()) {
      setFormError('Nội dung câu hỏi không được để trống.');
      return;
    }
    const options = structured ? entriesToOptions(entries) : form.rawOptions;
    const answerError = validateQuestionAnswer({
      questionType: form.questionType,
      rawOptions: options,
      correctAnswer: form.correctAnswer,
    });
    if (answerError) {
      setFormError(answerError);
      return;
    }
    const questionData = { options, correct_answer: form.correctAnswer, explanation: form.explanation };
    if (isEdit) {
      onSubmit({
        expected_version: question.current_version,
        content: form.content,
        question_data: { ...question.question_data, ...questionData },
        clo_ids: form.cloIds,
        change_note: form.changeNote.trim() || 'Quản trị viên cập nhật câu hỏi',
        // Chỉ gửi phân loại khi có đổi, để không đụng tới kiểm tra khớp tài liệu nguồn.
        ...(form.bloomLevel && form.bloomLevel !== original.bloomLevel ? { bloom_level: Number(form.bloomLevel) } : {}),
        ...(form.difficulty && form.difficulty !== original.difficulty ? { difficulty: form.difficulty } : {}),
      });
      return;
    }
    onSubmit({
      content: form.content.trim(),
      question_type: form.questionType,
      question_data: questionData,
      subject_id: form.subjectId,
      clo_ids: form.cloIds,
      ...(form.bloomLevel ? { bloom_level: Number(form.bloomLevel) } : {}),
      ...(form.difficulty ? { difficulty: form.difficulty } : {}),
    });
  };

  const answerInput = SINGLE_CHOICE_TYPES.has(form.questionType)
    ? 'radio'
    : MULTI_CHOICE_TYPES.has(form.questionType) ? 'checkbox' : '';
  const selectedAnswers = correctAnswerValues(form.correctAnswer);

  return (
    <div className="modal-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <form className="qbank-dialog" onSubmit={handleSubmit} role="dialog" aria-modal="true" aria-label={isEdit ? 'Sửa câu hỏi' : 'Thêm câu hỏi'}>
        <div className="qbank-dialog-head">
          <h2>{isEdit ? `Sửa câu hỏi ${question.question_code}` : 'Thêm câu hỏi'}</h2>
          <button type="button" className="qbank-icon-button" onClick={onClose} aria-label="Đóng">×</button>
        </div>

        {isEdit && question.review_status === 'APPROVED' && (
          <p className="qbank-note qbank-note--warning">
            Câu hỏi này đã được duyệt. Lưu thay đổi sẽ tạo phiên bản mới, đưa câu hỏi về trạng thái Nháp để duyệt lại,
            và báo cho chủ các đề thi đang dùng câu này.
          </p>
        )}

        <div className="qbank-form-grid">
          <label className="qbank-field">
            <span>Học phần</span>
            {isEdit ? (
              <input value={subject ? `${subject.subject_code} — ${subject.subject_name}` : 'Chưa gắn học phần'} disabled />
            ) : (
              <select value={form.subjectId} onChange={(event) => setForm({ ...form, subjectId: event.target.value, cloIds: [] })}>
                <option value="">Chọn học phần</option>
                {subjects.filter((item) => item.is_active !== false).map((item) => (
                  <option key={refId(item)} value={refId(item)}>{item.subject_code} — {item.subject_name}</option>
                ))}
              </select>
            )}
          </label>
          <label className="qbank-field">
            <span>Loại câu hỏi</span>
            {isEdit ? (
              <input value={questionTypeLabel(form.questionType)} disabled />
            ) : (
              <select value={form.questionType} onChange={(event) => setForm({ ...form, questionType: event.target.value, rawOptions: null, correctAnswer: '' })}>
                {QUESTION_TYPES.map((type) => <option key={type.backend} value={type.backend}>{type.label}</option>)}
              </select>
            )}
          </label>
          <label className="qbank-field">
            <span>Mức Bloom</span>
            <select value={form.bloomLevel} onChange={(event) => setField('bloomLevel', event.target.value)}>
              <option value="">Chưa chọn</option>
              {BLOOM_LEVELS.map((bloom) => <option key={bloom.level} value={String(bloom.level)}>{bloom.label}</option>)}
            </select>
          </label>
          <label className="qbank-field">
            <span>Độ khó</span>
            <select value={form.difficulty} onChange={(event) => setField('difficulty', event.target.value)}>
              <option value="">Chưa chọn</option>
              {DIFFICULTIES.map((difficulty) => <option key={difficulty.backend} value={difficulty.backend}>{difficulty.label}</option>)}
            </select>
          </label>
        </div>

        <label className="qbank-field">
          <span>Nội dung câu hỏi</span>
          <textarea rows={4} value={form.content} onChange={(event) => setField('content', event.target.value)} />
        </label>

        <div className="qbank-field">
          {structured && (
            <span>
              {answerInput === 'radio' && 'Lựa chọn — chọn một đáp án đúng'}
              {answerInput === 'checkbox' && 'Lựa chọn — tích các đáp án đúng (ít nhất 2)'}
              {!answerInput && 'Các mục của câu hỏi'}
            </span>
          )}
          {entries.map((entry) => (
            <div className="qbank-option-row" key={entry.key}>
              {answerInput && (
                <input
                  type={answerInput}
                  name="qbank-correct-answer"
                  aria-label={`Đáp án ${entry.key} đúng`}
                  checked={answerInput === 'radio' ? form.correctAnswer === entry.key : selectedAnswers.includes(entry.key)}
                  onChange={() => (answerInput === 'radio' ? setField('correctAnswer', entry.key) : toggleCorrect(entry.key))}
                />
              )}
              <b>{entry.key}</b>
              <input aria-label={`Nội dung lựa chọn ${entry.key}`} value={entry.value} onChange={(event) => updateOption(entry.key, event.target.value)} />
              {canChangeOptionCount && entries.length > 2 && (
                <button type="button" className="qbank-icon-button" onClick={() => removeOption(entry.key)} aria-label={`Xóa lựa chọn ${entry.key}`}>×</button>
              )}
            </div>
          ))}
          {canChangeOptionCount && entries.length < OPTION_KEYS.length && (
            <button type="button" className="qbank-link-button" onClick={addOption}>+ Thêm lựa chọn</button>
          )}
          {!answerInput && (
            <label className="qbank-field">
              <span>Đáp án đúng</span>
              <input value={form.correctAnswer} onChange={(event) => setField('correctAnswer', event.target.value)} />
            </label>
          )}
        </div>

        <label className="qbank-field">
          <span>Giải thích</span>
          <textarea rows={3} value={form.explanation} onChange={(event) => setField('explanation', event.target.value)} />
        </label>

        <div className="qbank-field">
          <span>Chuẩn đầu ra (CLO)</span>
          {outcomes.length > 0 ? outcomes.map((clo) => (
            <label className="qbank-check" key={refId(clo)}>
              <input type="checkbox" checked={form.cloIds.includes(refId(clo))} onChange={() => toggleClo(refId(clo))} />
              <span><b>{clo.clo_code}</b> {clo.description}</span>
            </label>
          )) : (
            <small>{form.subjectId ? 'Học phần này chưa có CLO.' : 'Chọn học phần để gắn CLO.'}</small>
          )}
        </div>

        {isEdit && (
          <label className="qbank-field">
            <span>Ghi chú thay đổi</span>
            <input maxLength={500} placeholder="Ví dụ: sửa lỗi chính tả ở phương án B" value={form.changeNote} onChange={(event) => setField('changeNote', event.target.value)} />
          </label>
        )}

        {(formError || error) && <p className="qbank-note qbank-note--error" role="alert">{formError || error}</p>}

        <div className="qbank-dialog-actions">
          <button type="button" className="jobs-secondary-button" onClick={onClose} disabled={saving}>Hủy</button>
          <button type="submit" className="jobs-primary-button" disabled={saving}>
            {saving ? 'Đang lưu...' : isEdit ? 'Lưu thay đổi' : 'Tạo câu hỏi'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default QuestionEditorDialog;
