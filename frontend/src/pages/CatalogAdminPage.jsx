import React, { useEffect, useMemo, useState } from 'react';
import {
  addSubjectChapter,
  addSubjectLearningOutcome,
  getCatalogOverview,
  saveAiModel,
  saveEvaluationPolicy,
  savePromptTemplate,
  saveSubject,
  updateSubject,
  updateSubjectChapter,
  updateSubjectLearningOutcome,
} from '../api/catalog';
import '../css/CatalogAdminPage.css';

const DEFAULT_WEIGHTS = {
  faithfulness: 0.35,
  contextual_relevancy: 0.20,
  answer_relevancy: 0.15,
  bloom_alignment: 0.15,
  clo_alignment: 0.15,
};

const DEFAULT_THRESHOLDS = { yellow_min: 0.6, green_min: 0.8, pass_min: 0.8 };
const EMPTY_SUBJECT_FORM = { id: '', subject_code: '', subject_name: '', description: '', is_active: true };
const EMPTY_CHAPTER_FORM = { id: '', chapter_code: '', chapter_name: '', sequence_no: 1, is_active: true };
const EMPTY_CLO_FORM = { id: '', clo_code: '', description: '', target_weight: 1, is_active: true };

function compactJson(value) {
  return JSON.stringify(value, null, 2);
}

function usageText(counts = {}) {
  const parts = [
    counts.documents ? `${counts.documents} tài liệu` : '',
    counts.questions ? `${counts.questions} câu hỏi` : '',
    counts.exams ? `${counts.exams} đề` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Chưa được dùng';
}

function childId(item) {
  return item?.id || item?._id || '';
}

function subjectToForm(subject) {
  if (!subject) return EMPTY_SUBJECT_FORM;
  return {
    id: subject.id,
    subject_code: subject.subject_code || '',
    subject_name: subject.subject_name || '',
    description: subject.description || '',
    is_active: subject.is_active !== false,
  };
}

function chapterToForm(chapter) {
  return {
    id: childId(chapter),
    chapter_code: chapter.chapter_code || '',
    chapter_name: chapter.chapter_name || '',
    sequence_no: chapter.sequence_no || 1,
    is_active: chapter.is_active !== false,
  };
}

function cloToForm(clo) {
  return {
    id: childId(clo),
    clo_code: clo.clo_code || '',
    description: clo.description || '',
    target_weight: clo.target_weight ?? 1,
    is_active: clo.is_active !== false,
  };
}

function CatalogAdminPage() {
  const [catalog, setCatalog] = useState({
    subjects: [],
    ai_models: [],
    prompt_templates: [],
    evaluation_policies: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeSubjectId, setActiveSubjectId] = useState('');
  const [subjectForm, setSubjectForm] = useState(EMPTY_SUBJECT_FORM);
  const [chapterForm, setChapterForm] = useState(EMPTY_CHAPTER_FORM);
  const [cloForm, setCloForm] = useState(EMPTY_CLO_FORM);
  const [modelForm, setModelForm] = useState({
    model_code: 'qwen',
    model_name: 'qwen2.5:7b',
    runtime: 'OLLAMA',
    kind: 'CHAT',
    revision: 'local',
    capabilities: 'QUESTION_GENERATION,QUESTION_EVALUATION',
    priority: 10,
  });
  const [selectedPromptKey, setSelectedPromptKey] = useState('');
  const [promptForm, setPromptForm] = useState({ template_key: '', kind: 'QUESTION_TYPE', name: '', prompt_body: '' });
  const [policyForm, setPolicyForm] = useState({
    policy_name: 'Default question quality policy',
    weights: compactJson(DEFAULT_WEIGHTS),
    thresholds: compactJson(DEFAULT_THRESHOLDS),
  });
  const [saving, setSaving] = useState(false);

  const activeSubject = useMemo(
    () => catalog.subjects.find((subject) => subject.id === activeSubjectId) || catalog.subjects[0],
    [catalog.subjects, activeSubjectId],
  );

  const promptOptions = useMemo(() => {
    const latestByKey = new Map();
    catalog.prompt_templates.forEach((template) => {
      const current = latestByKey.get(template.template_key);
      if (!current || template.version > current.version) latestByKey.set(template.template_key, template);
    });
    return Array.from(latestByKey.values());
  }, [catalog.prompt_templates]);

  const loadCatalog = async (preferredSubjectId = activeSubjectId) => {
    setLoading(true);
    setError('');
    try {
      const result = await getCatalogOverview();
      setCatalog(result);
      const nextActive = result.subjects?.find((subject) => subject.id === preferredSubjectId) || result.subjects?.[0];
      if (nextActive) {
        setActiveSubjectId(nextActive.id);
        setSubjectForm((current) => (
          current.id || (!current.subject_code && !current.subject_name)
            ? subjectToForm(nextActive)
            : current
        ));
      }
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu nền');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runSave = async (action) => {
    setSaving(true);
    setError('');
    try {
      const result = await action();
      await loadCatalog(result?.activeSubjectId);
    } catch (err) {
      setError(err.message || 'Lưu dữ liệu nền thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleSelectSubject = (subject) => {
    setActiveSubjectId(subject.id);
    setSubjectForm(subjectToForm(subject));
    setChapterForm(EMPTY_CHAPTER_FORM);
    setCloForm(EMPTY_CLO_FORM);
  };

  const handleNewSubject = () => {
    setSubjectForm(EMPTY_SUBJECT_FORM);
    setChapterForm(EMPTY_CHAPTER_FORM);
    setCloForm(EMPTY_CLO_FORM);
  };

  const handleSaveSubject = (event) => {
    event.preventDefault();
    runSave(async () => {
      const { id, ...payload } = subjectForm;
      const saved = id
        ? await updateSubject(id, payload)
        : await saveSubject(payload);
      setActiveSubjectId(saved.id);
      setSubjectForm(subjectToForm(saved));
      return { activeSubjectId: saved.id };
    });
  };

  const handleSaveChapter = (event) => {
    event.preventDefault();
    if (!activeSubject) return;
    runSave(async () => {
      const { id, ...payload } = chapterForm;
      const normalized = {
        ...payload,
        sequence_no: Number(chapterForm.sequence_no) || 1,
      };
      if (id) {
        await updateSubjectChapter(activeSubject.id, id, normalized);
      } else {
        await addSubjectChapter(activeSubject.id, normalized);
      }
      setChapterForm(EMPTY_CHAPTER_FORM);
    });
  };

  const handleSaveClo = (event) => {
    event.preventDefault();
    if (!activeSubject) return;
    runSave(async () => {
      const { id, ...payload } = cloForm;
      const normalized = {
        ...payload,
        target_weight: Number(cloForm.target_weight) || 0,
      };
      if (id) {
        await updateSubjectLearningOutcome(activeSubject.id, id, normalized);
      } else {
        await addSubjectLearningOutcome(activeSubject.id, normalized);
      }
      setCloForm(EMPTY_CLO_FORM);
    });
  };

  const toggleSubjectActive = () => {
    if (!activeSubject) return;
    runSave(async () => {
      const updated = await updateSubject(activeSubject.id, { is_active: !activeSubject.is_active });
      setSubjectForm(subjectToForm(updated));
    });
  };

  const toggleChapterActive = (chapter) => {
    if (!activeSubject) return;
    runSave(async () => updateSubjectChapter(
      activeSubject.id,
      childId(chapter),
      { is_active: chapter.is_active === false },
    ));
  };

  const toggleCloActive = (clo) => {
    if (!activeSubject) return;
    runSave(async () => updateSubjectLearningOutcome(
      activeSubject.id,
      childId(clo),
      { is_active: clo.is_active === false },
    ));
  };

  const handleSaveModel = (event) => {
    event.preventDefault();
    runSave(async () => saveAiModel({
      ...modelForm,
      capabilities: modelForm.capabilities.split(',').map((item) => item.trim()).filter(Boolean),
      priority: Number(modelForm.priority) || 0,
      config: { endpoint: 'http://localhost:11434/api/generate' },
      is_local: true,
      is_active: true,
    }));
  };

  const handleSelectPrompt = (templateKey) => {
    setSelectedPromptKey(templateKey);
    const selected = promptOptions.find((template) => template.template_key === templateKey);
    if (selected) {
      setPromptForm({
        template_key: selected.template_key,
        kind: selected.kind,
        name: selected.name,
        prompt_body: selected.prompt_body,
      });
    }
  };

  const handleSavePrompt = (event) => {
    event.preventDefault();
    runSave(async () => savePromptTemplate({ ...promptForm, create_new_version: true, is_active: true }));
  };

  const handleSavePolicy = (event) => {
    event.preventDefault();
    runSave(async () => saveEvaluationPolicy({
      policy_name: policyForm.policy_name,
      weights: JSON.parse(policyForm.weights),
      thresholds: JSON.parse(policyForm.thresholds),
      create_new_version: true,
      is_active: true,
    }));
  };

  return (
    <main className="catalog-page">
      <section className="catalog-header">
        <div>
          <span>Khu vực quản trị</span>
          <h1>Cấu hình dữ liệu nền</h1>
        </div>
        <button type="button" onClick={() => loadCatalog()} disabled={loading || saving}>Làm mới</button>
      </section>
      {error && <p className="catalog-error">{error}</p>}
      {loading ? (
        <p className="catalog-empty">Đang tải dữ liệu nền...</p>
      ) : (
        <section className="catalog-grid">
          <div className="catalog-card catalog-card--wide">
            <div className="catalog-card-title-row">
              <h2>Môn học / Chương / CLO</h2>
              <button type="button" className="catalog-ghost-button" onClick={handleNewSubject} disabled={saving}>
                Môn mới
              </button>
            </div>
            <form className="catalog-form catalog-form--inline" onSubmit={handleSaveSubject}>
              <input placeholder="Mã môn" value={subjectForm.subject_code} onChange={(e) => setSubjectForm({ ...subjectForm, subject_code: e.target.value })} />
              <input placeholder="Tên môn" value={subjectForm.subject_name} onChange={(e) => setSubjectForm({ ...subjectForm, subject_name: e.target.value })} />
              <input placeholder="Mô tả" value={subjectForm.description} onChange={(e) => setSubjectForm({ ...subjectForm, description: e.target.value })} />
              <label className="catalog-check">
                <input type="checkbox" checked={subjectForm.is_active} onChange={(e) => setSubjectForm({ ...subjectForm, is_active: e.target.checked })} />
                Đang dùng
              </label>
              <button type="submit" disabled={saving}>{subjectForm.id ? 'Lưu môn' : 'Tạo môn'}</button>
            </form>
            <div className="subject-layout">
              <div className="subject-list">
                {catalog.subjects.map((subject) => (
                  <button
                    type="button"
                    className={`${activeSubject?.id === subject.id ? 'active' : ''} ${subject.is_active === false ? 'inactive' : ''}`}
                    key={subject.id}
                    onClick={() => handleSelectSubject(subject)}
                  >
                    <b>{subject.subject_code}</b>
                    <span>{subject.subject_name}</span>
                    <small>{usageText(subject.usage_counts)}</small>
                  </button>
                ))}
              </div>
              <div className="subject-detail">
                <div className="catalog-detail-head">
                  <div>
                    <h3>{activeSubject?.subject_name || 'Chưa có môn'}</h3>
                    {activeSubject && <p>{usageText(activeSubject.usage_counts)}</p>}
                  </div>
                  {activeSubject && (
                    <button type="button" className="catalog-ghost-button" onClick={toggleSubjectActive} disabled={saving}>
                      {activeSubject.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                    </button>
                  )}
                </div>
                <div className="catalog-columns">
                  <form className="catalog-form" onSubmit={handleSaveChapter}>
                    <h4>{chapterForm.id ? 'Sửa chương' : 'Thêm chương'}</h4>
                    <input placeholder="CH01" value={chapterForm.chapter_code} onChange={(e) => setChapterForm({ ...chapterForm, chapter_code: e.target.value })} />
                    <input placeholder="Tên chương" value={chapterForm.chapter_name} onChange={(e) => setChapterForm({ ...chapterForm, chapter_name: e.target.value })} />
                    <input type="number" min="1" value={chapterForm.sequence_no} onChange={(e) => setChapterForm({ ...chapterForm, sequence_no: e.target.value })} />
                    <label className="catalog-check">
                      <input type="checkbox" checked={chapterForm.is_active} onChange={(e) => setChapterForm({ ...chapterForm, is_active: e.target.checked })} />
                      Đang dùng
                    </label>
                    <div className="catalog-form-actions">
                      {chapterForm.id && (
                        <button type="button" className="catalog-ghost-button" onClick={() => setChapterForm(EMPTY_CHAPTER_FORM)} disabled={saving}>
                          Hủy
                        </button>
                      )}
                      <button type="submit" disabled={!activeSubject || saving}>{chapterForm.id ? 'Lưu chương' : 'Thêm chương'}</button>
                    </div>
                  </form>
                  <form className="catalog-form" onSubmit={handleSaveClo}>
                    <h4>{cloForm.id ? 'Sửa CLO' : 'Thêm CLO'}</h4>
                    <input placeholder="CLO1" value={cloForm.clo_code} onChange={(e) => setCloForm({ ...cloForm, clo_code: e.target.value })} />
                    <input placeholder="Mô tả chuẩn đầu ra" value={cloForm.description} onChange={(e) => setCloForm({ ...cloForm, description: e.target.value })} />
                    <input type="number" min="0" max="1" step="0.05" value={cloForm.target_weight} onChange={(e) => setCloForm({ ...cloForm, target_weight: e.target.value })} />
                    <label className="catalog-check">
                      <input type="checkbox" checked={cloForm.is_active} onChange={(e) => setCloForm({ ...cloForm, is_active: e.target.checked })} />
                      Đang dùng
                    </label>
                    <div className="catalog-form-actions">
                      {cloForm.id && (
                        <button type="button" className="catalog-ghost-button" onClick={() => setCloForm(EMPTY_CLO_FORM)} disabled={saving}>
                          Hủy
                        </button>
                      )}
                      <button type="submit" disabled={!activeSubject || saving}>{cloForm.id ? 'Lưu CLO' : 'Thêm CLO'}</button>
                    </div>
                  </form>
                </div>
                <div className="catalog-list">
                  {(activeSubject?.chapters || []).map((chapter) => (
                    <article className={`catalog-list-item ${chapter.is_active === false ? 'inactive' : ''}`} key={childId(chapter)}>
                      <div>
                        <b>{chapter.chapter_code} - {chapter.chapter_name}</b>
                        <span>{usageText(chapter.usage_counts)}</span>
                      </div>
                      <div className="catalog-item-actions">
                        <button type="button" className="catalog-ghost-button" onClick={() => setChapterForm(chapterToForm(chapter))} disabled={saving}>
                          Sửa
                        </button>
                        <button type="button" className="catalog-ghost-button" onClick={() => toggleChapterActive(chapter)} disabled={saving}>
                          {chapter.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                        </button>
                      </div>
                    </article>
                  ))}
                  {(activeSubject?.learning_outcomes || []).map((clo) => (
                    <article className={`catalog-list-item ${clo.is_active === false ? 'inactive' : ''}`} key={childId(clo)}>
                      <div>
                        <b>{clo.clo_code}: {clo.description}</b>
                        <span>{usageText(clo.usage_counts)}</span>
                      </div>
                      <div className="catalog-item-actions">
                        <button type="button" className="catalog-ghost-button" onClick={() => setCloForm(cloToForm(clo))} disabled={saving}>
                          Sửa
                        </button>
                        <button type="button" className="catalog-ghost-button" onClick={() => toggleCloActive(clo)} disabled={saving}>
                          {clo.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="catalog-card">
            <h2>Mô hình AI</h2>
            <form className="catalog-form" onSubmit={handleSaveModel}>
              <input placeholder="Mã mô hình" value={modelForm.model_code} onChange={(e) => setModelForm({ ...modelForm, model_code: e.target.value })} />
              <input placeholder="Tên mô hình" value={modelForm.model_name} onChange={(e) => setModelForm({ ...modelForm, model_name: e.target.value })} />
              <input placeholder="Năng lực mô hình" value={modelForm.capabilities} onChange={(e) => setModelForm({ ...modelForm, capabilities: e.target.value })} />
              <input type="number" min="0" value={modelForm.priority} onChange={(e) => setModelForm({ ...modelForm, priority: e.target.value })} />
              <button type="submit" disabled={saving}>Lưu mô hình</button>
            </form>
            <div className="catalog-list">
              {catalog.ai_models.map((model) => (
                <span key={model._id}>{model.model_code} - {model.model_name}</span>
              ))}
            </div>
          </div>

          <div className="catalog-card catalog-card--wide">
            <h2>Mẫu prompt</h2>
            <div className="prompt-layout">
              <select value={selectedPromptKey} onChange={(e) => handleSelectPrompt(e.target.value)}>
                <option value="">Chọn prompt</option>
                {promptOptions.map((template) => (
                  <option key={template.template_key} value={template.template_key}>
                    {template.name || template.template_key} - phiên bản {template.version}
                  </option>
                ))}
              </select>
              <form className="catalog-form" onSubmit={handleSavePrompt}>
                <input placeholder="Mã prompt" value={promptForm.template_key} onChange={(e) => setPromptForm({ ...promptForm, template_key: e.target.value })} />
                <input placeholder="Nhóm prompt" value={promptForm.kind} onChange={(e) => setPromptForm({ ...promptForm, kind: e.target.value })} />
                <input placeholder="Tên prompt" value={promptForm.name} onChange={(e) => setPromptForm({ ...promptForm, name: e.target.value })} />
                <textarea rows={9} value={promptForm.prompt_body} onChange={(e) => setPromptForm({ ...promptForm, prompt_body: e.target.value })} />
                <button type="submit" disabled={saving}>Lưu phiên bản mới</button>
              </form>
            </div>
          </div>

          <div className="catalog-card">
            <h2>Bộ tiêu chí đánh giá</h2>
            <form className="catalog-form" onSubmit={handleSavePolicy}>
              <input value={policyForm.policy_name} onChange={(e) => setPolicyForm({ ...policyForm, policy_name: e.target.value })} />
              <textarea rows={7} value={policyForm.weights} onChange={(e) => setPolicyForm({ ...policyForm, weights: e.target.value })} />
              <textarea rows={5} value={policyForm.thresholds} onChange={(e) => setPolicyForm({ ...policyForm, thresholds: e.target.value })} />
              <button type="submit" disabled={saving}>Lưu phiên bản tiêu chí</button>
            </form>
            <div className="catalog-list">
              {catalog.evaluation_policies.map((policy) => (
                <span key={policy._id}>{policy.policy_name} - phiên bản {policy.version} {policy.is_active ? '(đang dùng)' : ''}</span>
              ))}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}

export default CatalogAdminPage;
