import React, { useEffect, useMemo, useState } from 'react';
import {
  addSubjectChapter,
  addSubjectLearningOutcome,
  getCatalogOverview,
  saveAiModel,
  saveEvaluationPolicy,
  savePromptTemplate,
  saveSubject,
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

function compactJson(value) {
  return JSON.stringify(value, null, 2);
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
  const [subjectForm, setSubjectForm] = useState({ subject_code: 'CTDL', subject_name: 'Cấu trúc dữ liệu', description: '' });
  const [chapterForm, setChapterForm] = useState({ chapter_code: '', chapter_name: '', sequence_no: 1 });
  const [cloForm, setCloForm] = useState({ clo_code: '', description: '', target_weight: 1 });
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

  const loadCatalog = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await getCatalogOverview();
      setCatalog(result);
      if (!activeSubjectId && result.subjects?.[0]) setActiveSubjectId(result.subjects[0].id);
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
      await action();
      await loadCatalog();
    } catch (err) {
      setError(err.message || 'Lưu dữ liệu nền thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSubject = (event) => {
    event.preventDefault();
    runSave(async () => {
      const saved = await saveSubject({ ...subjectForm, is_active: true });
      setActiveSubjectId(saved.id);
    });
  };

  const handleAddChapter = (event) => {
    event.preventDefault();
    if (!activeSubject) return;
    runSave(async () => addSubjectChapter(activeSubject.id, {
      ...chapterForm,
      sequence_no: Number(chapterForm.sequence_no) || 1,
    }));
  };

  const handleAddClo = (event) => {
    event.preventDefault();
    if (!activeSubject) return;
    runSave(async () => addSubjectLearningOutcome(activeSubject.id, {
      ...cloForm,
      target_weight: Number(cloForm.target_weight) || 0,
    }));
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
        <button type="button" onClick={loadCatalog} disabled={loading || saving}>Làm mới</button>
      </section>
      {error && <p className="catalog-error">{error}</p>}
      {loading ? (
        <p className="catalog-empty">Đang tải dữ liệu nền...</p>
      ) : (
        <section className="catalog-grid">
          <div className="catalog-card catalog-card--wide">
            <h2>Môn học / Chương / CLO</h2>
            <form className="catalog-form catalog-form--inline" onSubmit={handleSaveSubject}>
              <input placeholder="Mã môn" value={subjectForm.subject_code} onChange={(e) => setSubjectForm({ ...subjectForm, subject_code: e.target.value })} />
              <input placeholder="Tên môn" value={subjectForm.subject_name} onChange={(e) => setSubjectForm({ ...subjectForm, subject_name: e.target.value })} />
              <input placeholder="Mô tả" value={subjectForm.description} onChange={(e) => setSubjectForm({ ...subjectForm, description: e.target.value })} />
              <button type="submit" disabled={saving}>Lưu môn</button>
            </form>
            <div className="subject-layout">
              <div className="subject-list">
                {catalog.subjects.map((subject) => (
                  <button
                    type="button"
                    className={activeSubject?.id === subject.id ? 'active' : ''}
                    key={subject.id}
                    onClick={() => setActiveSubjectId(subject.id)}
                  >
                    <b>{subject.subject_code}</b>
                    <span>{subject.subject_name}</span>
                  </button>
                ))}
              </div>
              <div className="subject-detail">
                <h3>{activeSubject?.subject_name || 'Chưa có môn'}</h3>
                <div className="catalog-columns">
                  <form className="catalog-form" onSubmit={handleAddChapter}>
                    <h4>Thêm chương</h4>
                    <input placeholder="CH01" value={chapterForm.chapter_code} onChange={(e) => setChapterForm({ ...chapterForm, chapter_code: e.target.value })} />
                    <input placeholder="Tên chương" value={chapterForm.chapter_name} onChange={(e) => setChapterForm({ ...chapterForm, chapter_name: e.target.value })} />
                    <input type="number" min="1" value={chapterForm.sequence_no} onChange={(e) => setChapterForm({ ...chapterForm, sequence_no: e.target.value })} />
                    <button type="submit" disabled={!activeSubject || saving}>Thêm chương</button>
                  </form>
                  <form className="catalog-form" onSubmit={handleAddClo}>
                    <h4>Thêm CLO</h4>
                    <input placeholder="CLO1" value={cloForm.clo_code} onChange={(e) => setCloForm({ ...cloForm, clo_code: e.target.value })} />
                    <input placeholder="Mô tả chuẩn đầu ra" value={cloForm.description} onChange={(e) => setCloForm({ ...cloForm, description: e.target.value })} />
                    <input type="number" min="0" max="1" step="0.05" value={cloForm.target_weight} onChange={(e) => setCloForm({ ...cloForm, target_weight: e.target.value })} />
                    <button type="submit" disabled={!activeSubject || saving}>Thêm CLO</button>
                  </form>
                </div>
                <div className="catalog-list">
                  {(activeSubject?.chapters || []).map((chapter) => (
                    <span key={chapter.id || chapter._id}>{chapter.chapter_code} - {chapter.chapter_name}</span>
                  ))}
                  {(activeSubject?.learning_outcomes || []).map((clo) => (
                    <span key={clo.id || clo._id}>{clo.clo_code}: {clo.description}</span>
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
