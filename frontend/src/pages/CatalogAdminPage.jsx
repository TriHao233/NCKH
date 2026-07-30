import React, { useEffect, useMemo, useState } from 'react';
import {
  activateEvaluationPolicy,
  activatePromptTemplate,
  addSubjectChapter,
  addSubjectLearningOutcome,
  checkAiModelHealth,
  getCatalogOverview,
  saveAiModel,
  saveEvaluationPolicy,
  savePromptTemplate,
  saveSubject,
  setAiModelActive,
  testPromptTemplate,
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
const POLICY_WEIGHT_FIELDS = [
  ['faithfulness', 'Bám sát nguồn'],
  ['contextual_relevancy', 'Liên quan ngữ cảnh'],
  ['answer_relevancy', 'Độ phù hợp đáp án'],
  ['bloom_alignment', 'Khớp Bloom'],
  ['clo_alignment', 'Khớp CLO'],
];
const POLICY_THRESHOLD_FIELDS = [
  ['yellow_min', 'Tối thiểu mức vàng'],
  ['green_min', 'Tối thiểu mức xanh'],
  ['pass_min', 'Ngưỡng đạt'],
];
const EMPTY_SUBJECT_FORM = { id: '', subject_code: '', subject_name: '', description: '', is_active: true };
const EMPTY_CHAPTER_FORM = { id: '', chapter_code: '', chapter_name: '', sequence_no: 1, is_active: true };
const EMPTY_CLO_FORM = { id: '', clo_code: '', description: '', target_weight: 1, is_active: true };

function usageText(counts = {}) {
  const parts = [
    counts.documents ? `${counts.documents} tài liệu` : '',
    counts.questions ? `${counts.questions} câu hỏi` : '',
    counts.exams ? `${counts.exams} đề` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Chưa được dùng';
}

function usageTotal(counts = {}) {
  return Object.values(counts).reduce((total, value) => total + Number(value || 0), 0);
}

function childId(item) {
  return item?.id || item?._id || '';
}

function factoryText(model) {
  const status = model?.factory_status;
  if (!status) return 'Chưa kiểm tra factory';
  if (!status.supported) return status.error || 'Factory chưa hỗ trợ';
  const runtime = status.runtime || {};
  return `${runtime.provider_class || 'Provider'}${runtime.model_name ? ` · ${runtime.model_name}` : ''}`;
}

function healthText(model) {
  const health = model?.last_health_check;
  if (!health) return 'Chưa health-check';
  if (
    health.status === 'OK'
    && (!health.config_hash || health.config_hash !== model.config_hash)
  ) {
    return 'Health-check không còn khớp cấu hình';
  }
  return health.status === 'OK'
    ? `OK · ${health.latency_ms || 0}ms`
    : `${health.status || 'FAILED'}${health.error ? ` · ${health.error}` : ''}`;
}

function modelHealthReady(model) {
  const health = model?.last_health_check;
  return Boolean(
    health?.status === 'OK'
    && health.config_hash
    && health.config_hash === model?.config_hash,
  );
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
    is_active: false,
  });
  const [selectedPromptKey, setSelectedPromptKey] = useState('');
  const [selectedPromptVersion, setSelectedPromptVersion] = useState(null);
  const [promptForm, setPromptForm] = useState({ template_key: '', kind: 'QUESTION_TYPE', name: '', prompt_body: '' });
  const [policyForm, setPolicyForm] = useState({
    policy_name: 'Default question quality policy',
    weights: { ...DEFAULT_WEIGHTS },
    thresholds: { ...DEFAULT_THRESHOLDS },
  });
  const [healthCheckingCode, setHealthCheckingCode] = useState('');
  const [modelHealth, setModelHealth] = useState(null);
  const [promptTesting, setPromptTesting] = useState(false);
  const [promptPreview, setPromptPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  const activeSubject = useMemo(
    () => catalog.subjects.find((subject) => subject.id === activeSubjectId) || catalog.subjects[0],
    [catalog.subjects, activeSubjectId],
  );
  const runtimeConfig = catalog.runtime_config || {};
  const policyWeightTotal = Object.values(policyForm.weights)
    .reduce((total, value) => total + Number(value || 0), 0);
  const policyThresholdsValid = (
    Number(policyForm.thresholds.yellow_min) <= Number(policyForm.thresholds.green_min)
    && Number(policyForm.thresholds.green_min) <= Number(policyForm.thresholds.pass_min)
  );
  const policyFormValid = (
    policyForm.policy_name.trim().length > 0
    && Math.abs(policyWeightTotal - 1) < 0.000001
    && policyThresholdsValid
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
    if (
      activeSubject.is_active !== false
      && usageTotal(activeSubject.usage_counts) > 0
      && !window.confirm(
        `Tạm khóa ${activeSubject.subject_code}? Đang liên quan: ${usageText(activeSubject.usage_counts)}. Dữ liệu cũ vẫn được giữ nhưng không thể chọn cho dữ liệu mới.`,
      )
    ) return;
    runSave(async () => {
      const updated = await updateSubject(activeSubject.id, { is_active: !activeSubject.is_active });
      setSubjectForm(subjectToForm(updated));
    });
  };

  const toggleChapterActive = (chapter) => {
    if (!activeSubject) return;
    if (
      chapter.is_active !== false
      && usageTotal(chapter.usage_counts) > 0
      && !window.confirm(
        `Tạm khóa chương ${chapter.chapter_code}? Đang liên quan: ${usageText(chapter.usage_counts)}.`,
      )
    ) return;
    runSave(async () => updateSubjectChapter(
      activeSubject.id,
      childId(chapter),
      { is_active: chapter.is_active === false },
    ));
  };

  const toggleCloActive = (clo) => {
    if (!activeSubject) return;
    if (
      clo.is_active !== false
      && usageTotal(clo.usage_counts) > 0
      && !window.confirm(
        `Tạm khóa ${clo.clo_code}? Đang liên quan: ${usageText(clo.usage_counts)}.`,
      )
    ) return;
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
      is_active: false,
    }));
  };

  const handleSelectModel = (model) => {
    setModelForm({
      model_code: model.model_code || '',
      model_name: model.model_name || '',
      runtime: model.runtime || 'OLLAMA',
      kind: model.kind || 'CHAT',
      revision: model.revision || 'local',
      capabilities: (model.capabilities || []).join(','),
      priority: model.priority ?? 10,
      is_active: false,
    });
  };

  const toggleModelActive = (model) => {
    if (model.is_active === false && !modelHealthReady(model)) {
      setError('Model phải health-check thành công với cấu hình hiện tại trước khi kích hoạt.');
      return;
    }
    runSave(async () => setAiModelActive({
      model_code: model.model_code,
      is_active: model.is_active === false,
    }));
  };

  const handleCheckModelHealth = async (model) => {
    setHealthCheckingCode(model.model_code);
    setError('');
    try {
      const result = await checkAiModelHealth({
        model_code: model.model_code,
        timeout_seconds: 10,
      });
      setModelHealth(result);
      await loadCatalog();
    } catch (err) {
      setError(err.message || 'Health-check model thất bại');
    } finally {
      setHealthCheckingCode('');
    }
  };

  const handleSelectPrompt = (templateKey) => {
    setSelectedPromptKey(templateKey);
    const selected = promptOptions.find((template) => template.template_key === templateKey);
    if (selected) {
      setSelectedPromptVersion(selected.version);
      setPromptForm({
        template_key: selected.template_key,
        kind: selected.kind,
        name: selected.name,
        prompt_body: selected.prompt_body,
      });
    } else {
      setSelectedPromptVersion(null);
    }
  };

  const handleEditPromptVersion = (template) => {
    setSelectedPromptKey(template.template_key);
    setSelectedPromptVersion(template.version);
    setPromptForm({
      template_key: template.template_key,
      kind: template.kind,
      name: template.name,
      prompt_body: template.prompt_body,
    });
  };

  const handleSavePrompt = (event) => {
    event.preventDefault();
    runSave(async () => {
      const saved = await savePromptTemplate({
        ...promptForm,
        create_new_version: true,
        is_active: false,
      });
      setSelectedPromptKey(saved.template_key);
      setSelectedPromptVersion(saved.version);
      return saved;
    });
  };

  const handleActivatePrompt = (template, isActive = true) => {
    runSave(async () => activatePromptTemplate({
      template_key: template.template_key,
      version: template.version,
      is_active: isActive,
    }));
  };

  const handleTestPrompt = async () => {
    const selected = catalog.prompt_templates.find((template) => (
      template.template_key === selectedPromptKey
      && template.version === selectedPromptVersion
    ));
    if (!selected) {
      setError('Hãy chọn một phiên bản prompt đã lưu trước khi test-build.');
      return;
    }
    setPromptTesting(true);
    setError('');
    try {
      const result = await testPromptTemplate({
        template_key: selected.template_key,
        version: selected.version,
      });
      setPromptPreview(result);
      await loadCatalog();
    } catch (err) {
      setError(err.message || 'Không build được prompt mẫu');
    } finally {
      setPromptTesting(false);
    }
  };

  const handleSavePolicy = (event) => {
    event.preventDefault();
    runSave(async () => saveEvaluationPolicy({
      policy_name: policyForm.policy_name.trim(),
      weights: Object.fromEntries(
        Object.entries(policyForm.weights).map(([key, value]) => [key, Number(value)]),
      ),
      thresholds: Object.fromEntries(
        Object.entries(policyForm.thresholds).map(([key, value]) => [key, Number(value)]),
      ),
      create_new_version: true,
      is_active: true,
    }));
  };

  const handleEditPolicy = (policy) => {
    setPolicyForm({
      policy_name: policy.policy_name,
      weights: { ...(policy.weights || DEFAULT_WEIGHTS) },
      thresholds: { ...(policy.thresholds || DEFAULT_THRESHOLDS) },
    });
  };

  const handleActivatePolicy = (policy) => {
    runSave(async () => activateEvaluationPolicy({
      policy_name: policy.policy_name,
      version: policy.version,
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
          <div className="catalog-card catalog-card--wide catalog-runtime-panel">
            <div className="catalog-card-title-row">
              <h2>Runtime đang dùng</h2>
              <span className={`catalog-status ${runtimeConfig.prompt_source === 'db' ? 'ok' : 'warn'}`}>
                PROMPT_SOURCE={runtimeConfig.prompt_source || 'file'}
              </span>
            </div>
            <div className="runtime-grid">
              <div>
                <small>Sinh câu hỏi</small>
                <b>{runtimeConfig.generation_model_provider || '--'}</b>
                <span>{runtimeConfig.generation_factory?.runtime?.provider_class || factoryText(runtimeConfig.generation_catalog_model)}</span>
              </div>
              <div>
                <small>Đánh giá AI</small>
                <b>{runtimeConfig.evaluation_model_provider || '--'}</b>
                <span>{runtimeConfig.evaluation_factory?.runtime?.provider_class || factoryText(runtimeConfig.evaluation_catalog_model)}</span>
              </div>
              <div>
                <small>Prompt DB active</small>
                <b>{runtimeConfig.active_prompt_count ?? 0}</b>
                <span>{runtimeConfig.prompt_source === 'db' ? 'Có hiệu lực runtime' : 'Chưa có hiệu lực runtime'}</span>
              </div>
              <div>
                <small>Policy active</small>
                <b>{runtimeConfig.active_evaluation_policy?.policy_name || '--'}</b>
                <span>Phiên bản {runtimeConfig.active_evaluation_policy?.version || 1}</span>
              </div>
            </div>
            {(runtimeConfig.warnings || []).length > 0 && (
              <div className="catalog-warning-list">
                {runtimeConfig.warnings.map((warning) => (
                  <span key={warning}>{warning}</span>
                ))}
              </div>
            )}
          </div>

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
              <p className="catalog-form-hint">Mô hình được lưu ở trạng thái chưa kích hoạt. Hãy health-check trước khi dùng.</p>
              <button type="submit" disabled={saving}>Lưu mô hình</button>
            </form>
            <div className="catalog-list">
              {catalog.ai_models.map((model) => (
                <article className={`catalog-list-item ${model.is_active === false ? 'inactive' : ''}`} key={model._id || model.model_code}>
                  <div>
                    <b>{model.model_code} - {model.model_name}</b>
                    <span>{factoryText(model)}</span>
                    <span>{healthText(model)}</span>
                  </div>
                  <div className="catalog-item-actions">
                    <button type="button" className="catalog-ghost-button" onClick={() => handleSelectModel(model)} disabled={saving}>
                      Sửa
                    </button>
                    <button
                      type="button"
                      className="catalog-ghost-button"
                      onClick={() => toggleModelActive(model)}
                      disabled={saving || (model.is_active === false && !modelHealthReady(model))}
                      title={model.is_active === false && !modelHealthReady(model)
                        ? 'Cần health-check thành công trước khi kích hoạt'
                        : ''}
                    >
                      {model.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                    </button>
                    <button type="button" onClick={() => handleCheckModelHealth(model)} disabled={saving || healthCheckingCode === model.model_code}>
                      {healthCheckingCode === model.model_code ? 'Đang kiểm tra...' : 'Health-check'}
                    </button>
                  </div>
                </article>
              ))}
            </div>
            {modelHealth && (
              <p className={`catalog-result ${modelHealth.status === 'OK' ? 'ok' : 'warn'}`}>
                {modelHealth.model_code}: {modelHealth.status} · {modelHealth.latency_ms || 0}ms
              </p>
            )}
          </div>

          <div className="catalog-card catalog-card--wide">
            <div className="catalog-card-title-row">
              <h2>Mẫu prompt</h2>
              <button
                type="button"
                className="catalog-ghost-button"
                onClick={handleTestPrompt}
                disabled={promptTesting || !selectedPromptKey || !selectedPromptVersion}
              >
                {promptTesting ? 'Đang build...' : 'Test-build phiên bản đã chọn'}
              </button>
            </div>
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
            {promptPreview && (
              <div className="prompt-preview">
                <div className="catalog-card-title-row">
                  <b>Prompt preview · {promptPreview.length} ký tự</b>
                  <span className={`catalog-status ${promptPreview.prompt_source === 'db' ? 'ok' : 'warn'}`}>
                    {promptPreview.prompt_source}
                  </span>
                </div>
                <pre>{promptPreview.rendered_prompt}</pre>
              </div>
            )}
            <div className="catalog-list">
              {catalog.prompt_templates.map((template) => (
                <article className={`catalog-list-item ${template.is_active ? '' : 'inactive'}`} key={`${template.template_key}-${template.version}`}>
                  <div>
                    <b>{template.name || template.template_key}</b>
                    <span>
                      {template.template_key} · phiên bản {template.version}
                      {template.is_active ? ' · Đang áp dụng' : ' · Bản nháp'}
                    </span>
                    <span>
                      Test-build: {template.last_test_build?.status === 'OK'
                        && template.last_test_build?.content_hash === template.content_hash
                        ? 'Đạt'
                        : 'Chưa đạt'}
                    </span>
                  </div>
                  <div className="catalog-item-actions">
                    <button type="button" className="catalog-ghost-button" onClick={() => handleEditPromptVersion(template)} disabled={saving}>
                      Sửa
                    </button>
                    <button
                      type="button"
                      onClick={() => handleActivatePrompt(template, !template.is_active)}
                      disabled={
                        saving
                        || (
                          !template.is_active
                          && !(
                            template.last_test_build?.status === 'OK'
                            && template.last_test_build?.content_hash === template.content_hash
                          )
                        )
                      }
                    >
                      {template.is_active ? 'Ngừng áp dụng' : 'Kích hoạt'}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="catalog-card">
            <h2>Bộ tiêu chí đánh giá</h2>
            <form className="catalog-form" onSubmit={handleSavePolicy}>
              <label className="policy-field">
                <span>Tên bộ tiêu chí</span>
                <input
                  required
                  value={policyForm.policy_name}
                  onChange={(e) => setPolicyForm({ ...policyForm, policy_name: e.target.value })}
                />
              </label>
              <fieldset className="policy-fieldset">
                <legend>Trọng số</legend>
                <div className="policy-field-grid">
                  {POLICY_WEIGHT_FIELDS.map(([key, label]) => (
                    <label className="policy-field" key={key}>
                      <span>{label}</span>
                      <input
                        required
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        value={policyForm.weights[key]}
                        onChange={(e) => setPolicyForm({
                          ...policyForm,
                          weights: { ...policyForm.weights, [key]: e.target.value },
                        })}
                      />
                    </label>
                  ))}
                </div>
                <p className={`policy-total ${Math.abs(policyWeightTotal - 1) < 0.000001 ? 'ok' : 'warn'}`}>
                  Tổng trọng số: {policyWeightTotal.toFixed(2)} / 1.00
                </p>
              </fieldset>
              <fieldset className="policy-fieldset">
                <legend>Ngưỡng đánh giá</legend>
                <div className="policy-field-grid">
                  {POLICY_THRESHOLD_FIELDS.map(([key, label]) => (
                    <label className="policy-field" key={key}>
                      <span>{label}</span>
                      <input
                        required
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        value={policyForm.thresholds[key]}
                        onChange={(e) => setPolicyForm({
                          ...policyForm,
                          thresholds: { ...policyForm.thresholds, [key]: e.target.value },
                        })}
                      />
                    </label>
                  ))}
                </div>
                {!policyThresholdsValid && (
                  <p className="policy-total warn">
                    Cần thỏa: mức vàng ≤ mức xanh ≤ ngưỡng đạt.
                  </p>
                )}
              </fieldset>
              <button type="submit" disabled={saving || !policyFormValid}>Lưu phiên bản tiêu chí</button>
            </form>
            <div className="catalog-list">
              {catalog.evaluation_policies.map((policy) => (
                <article className={`catalog-list-item ${policy.is_active ? '' : 'inactive'}`} key={policy._id || `${policy.policy_name}-${policy.version}`}>
                  <div>
                    <b>{policy.policy_name}</b>
                    <span>Phiên bản {policy.version} {policy.is_active ? '· đang dùng' : ''}</span>
                  </div>
                  <div className="catalog-item-actions">
                    <button type="button" className="catalog-ghost-button" onClick={() => handleEditPolicy(policy)} disabled={saving}>
                      Sửa
                    </button>
                    <button type="button" onClick={() => handleActivatePolicy(policy)} disabled={saving || policy.is_active}>
                      {policy.is_active ? 'Đang active' : 'Kích hoạt'}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}

export default CatalogAdminPage;
