import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faHeartPulse, faPen, faPlus, faRotateRight } from '@fortawesome/free-solid-svg-icons';
import {
  activateEvaluationPolicy,
  activatePromptTemplate,
  checkAiModelHealth,
  getCatalogOverview,
  saveAiModel,
  saveEvaluationPolicy,
  savePromptTemplate,
  setAiModelActive,
  testPromptTemplate,
} from '../api/catalog';
import WorkspaceHero from '../components/workspace/WorkspaceHero';
import Drawer from '../components/workspace/Drawer';
import MoreMenu from '../components/workspace/MoreMenu';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../components/workspace/Feedback';
import { useConfirm, useFlash } from '../components/workspace/Dialog';
import { Tabs } from '../components/workspace/Navigation';
import { diffLines } from '../features/admin/textDiff';
import { REVIEW_CRITERIA, formatDateTime } from '../features/review/reviewModel';
import '../css/workspace.css';
import '../css/AdminPages.css';

const TABS = [
  { value: 'models', label: 'Mô hình' },
  { value: 'prompts', label: 'Mẫu prompt' },
  { value: 'policies', label: 'Tiêu chí đánh giá' },
];

const CAPABILITY_LABEL = {
  QUESTION_GENERATION: 'Sinh câu hỏi',
  QUESTION_EVALUATION: 'Đánh giá câu hỏi',
};

const DEFAULT_WEIGHTS = {
  faithfulness: 0.35,
  contextual_relevancy: 0.2,
  answer_relevancy: 0.15,
  bloom_alignment: 0.15,
  clo_alignment: 0.15,
};

const DEFAULT_THRESHOLDS = { pass_min: 0.65, green_min: 0.75, yellow_min: 0.5 };

const THRESHOLD_FIELDS = [
  { key: 'pass_min', label: 'Điểm đạt tối thiểu', hint: 'AI đề xuất đạt khi tổng điểm từ mức này.' },
  { key: 'green_min', label: 'Ngưỡng "Đạt tốt"', hint: 'Từ mức này câu hỏi được tô xanh.' },
  { key: 'yellow_min', label: 'Ngưỡng "Cần xem lại"', hint: 'Dưới mức này câu hỏi bị đánh dấu rủi ro cao.' },
];

const EMPTY_MODEL = {
  model_code: '',
  model_name: '',
  display_name: '',
  description: '',
  runtime: 'OLLAMA',
  kind: 'CHAT',
  revision: 'local',
  capabilities: ['QUESTION_GENERATION'],
  priority: 10,
  is_active: true,
  config: { endpoint: '', timeout_seconds: 300, temperature: 0, num_predict: 900, max_output_tokens: 2048 },
};

function modelToForm(model) {
  return {
    model_code: model.model_code || '',
    model_name: model.model_name || '',
    display_name: model.display_name || model.model_name || '',
    description: model.description || '',
    runtime: model.runtime || 'OLLAMA',
    kind: model.kind || 'CHAT',
    revision: model.revision || 'local',
    capabilities: model.capabilities?.length ? [...model.capabilities] : ['QUESTION_GENERATION'],
    priority: model.priority ?? 10,
    is_active: model.is_active !== false,
    config: {
      endpoint: model.config?.endpoint || '',
      timeout_seconds: model.config?.timeout_seconds ?? 300,
      temperature: model.config?.temperature ?? 0,
      num_predict: model.config?.num_predict ?? 900,
      max_output_tokens: model.config?.max_output_tokens ?? 2048,
    },
  };
}

function healthOf(model) {
  const health = model?.last_health_check;
  if (!health) return { tone: 'outline', text: 'Chưa kiểm tra' };
  if (health.status === 'OK') return { tone: 'success', text: `Kết nối tốt, ${health.latency_ms || 0} ms` };
  return { tone: 'danger', text: health.error ? `Lỗi: ${health.error}` : 'Không phản hồi' };
}

function criterionLabel(key) {
  return REVIEW_CRITERIA.find((item) => item.key === key)?.label || key;
}

function policyForm(policy) {
  const weights = { ...DEFAULT_WEIGHTS, ...(policy?.weights || {}) };
  const thresholds = { ...DEFAULT_THRESHOLDS, ...(policy?.thresholds || {}) };
  return {
    policy_name: policy?.policy_name || 'Tiêu chí chất lượng câu hỏi',
    weights: Object.fromEntries(Object.entries(weights).map(([key, value]) => [key, String(value)])),
    thresholds: Object.fromEntries(Object.entries(thresholds).map(([key, value]) => [key, String(value)])),
  };
}

function AiConfigPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = TABS.some((item) => item.value === searchParams.get('tab')) ? searchParams.get('tab') : 'models';
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState('');
  const [modelDrawer, setModelDrawer] = useState(null);
  const [promptKey, setPromptKey] = useState('');
  const [promptEditor, setPromptEditor] = useState(null);
  const [compare, setCompare] = useState({ from: '', to: '' });
  const [promptPreview, setPromptPreview] = useState(null);
  const [policyEditor, setPolicyEditor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      setCatalog(await getCatalogOverview());
    } catch (err) {
      setLoadError(err.message || 'Không tải được cấu hình AI.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runtime = catalog?.runtime_config || {};
  const models = catalog?.ai_models || [];
  const policies = catalog?.evaluation_policies || [];
  const activePolicy = policies.find((policy) => policy.is_active) || null;

  const promptGroups = useMemo(() => {
    const map = new Map();
    (catalog?.prompt_templates || []).forEach((template) => {
      const list = map.get(template.template_key) || [];
      list.push(template);
      map.set(template.template_key, list);
    });
    return Array.from(map.entries())
      .map(([key, versions]) => ({ key, versions: versions.sort((a, b) => b.version - a.version) }))
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [catalog]);

  const selectedGroup = promptGroups.find((group) => group.key === promptKey) || promptGroups[0] || null;

  useEffect(() => {
    if (!selectedGroup) return;
    const active = selectedGroup.versions.find((item) => item.is_active) || selectedGroup.versions[0];
    const previous = selectedGroup.versions.find((item) => item.version !== active.version);
    setCompare({ from: previous ? String(previous.version) : String(active.version), to: String(active.version) });
    setPromptPreview(null);
  }, [selectedGroup?.key, catalog]); // eslint-disable-line react-hooks/exhaustive-deps

  const setTab = (value) => setSearchParams(value === 'models' ? {} : { tab: value }, { replace: true });

  const run = async (key, action, successMessage) => {
    setBusy(key);
    clearFlash();
    try {
      await action();
      await load();
      if (successMessage) showFlash('success', successMessage);
      return true;
    } catch (err) {
      showFlash('error', err.message || 'Thao tác thất bại.');
      return false;
    } finally {
      setBusy('');
    }
  };

  // ─── Mô hình ─────────────────────────────────────────────────
  const updateModel = (patch) => setModelDrawer((current) => ({ ...current, error: '', form: { ...current.form, ...patch } }));
  const updateModelConfig = (patch) => setModelDrawer((current) => ({ ...current, error: '', form: { ...current.form, config: { ...current.form.config, ...patch } } }));

  const saveModel = async () => {
    const { form } = modelDrawer;
    let error = '';
    if (!form.display_name.trim() || !form.model_code.trim() || !form.model_name.trim()) error = 'Nhập tên hiển thị, mã cấu hình và tên mô hình.';
    else if (!form.capabilities.length) error = 'Chọn ít nhất một mục đích sử dụng.';
    else if (form.runtime === 'OLLAMA' && form.config.endpoint.trim() && !/^https?:\/\//.test(form.config.endpoint.trim())) error = 'Địa chỉ Ollama phải bắt đầu bằng http:// hoặc https://.';
    if (error) {
      setModelDrawer((current) => ({ ...current, error }));
      return;
    }
    const config = {
      timeout_seconds: Number(form.config.timeout_seconds) || 300,
      temperature: Number(form.config.temperature) || 0,
      ...(form.runtime === 'GEMINI'
        ? { max_output_tokens: Number(form.config.max_output_tokens) || 2048 }
        : { num_predict: Number(form.config.num_predict) || 900 }),
      ...(form.runtime === 'OLLAMA' && form.config.endpoint.trim() ? { endpoint: form.config.endpoint.trim() } : {}),
    };
    setBusy('model');
    try {
      await saveAiModel({
        ...form,
        model_code: form.model_code.trim(),
        model_name: form.model_name.trim(),
        display_name: form.display_name.trim(),
        priority: Number(form.priority) || 0,
        config,
        is_local: form.runtime === 'OLLAMA',
      });
      setModelDrawer(null);
      showFlash('success', 'Đã lưu mô hình.');
      await load();
    } catch (err) {
      setModelDrawer((current) => ({ ...current, error: err.message || 'Lưu thất bại.' }));
    } finally {
      setBusy('');
    }
  };

  const checkModel = async (model) => {
    setBusy(`health:${model.model_code}`);
    clearFlash();
    try {
      const result = await checkAiModelHealth({ model_code: model.model_code, timeout_seconds: 10 });
      showFlash(result.status === 'OK' ? 'success' : 'warn', result.status === 'OK'
        ? `${model.display_name || model.model_code} phản hồi sau ${result.latency_ms || 0} ms.`
        : `${model.display_name || model.model_code} chưa sẵn sàng${result.error ? `: ${result.error}` : '.'}`);
      await load();
    } catch (err) {
      showFlash('error', err.message || 'Không kiểm tra được kết nối.');
    } finally {
      setBusy('');
    }
  };

  const toggleModel = async (model) => {
    const turningOff = model.is_active !== false;
    if (turningOff) {
      const accepted = await confirm({
        title: 'Tắt mô hình',
        description: `${model.display_name || model.model_code} sẽ không còn trong lựa chọn khi sinh hoặc đánh giá câu hỏi. Các tác vụ đang chạy không bị ảnh hưởng.`,
        confirmLabel: 'Tắt mô hình',
        tone: 'danger',
      });
      if (!accepted) return;
    }
    await run('model-toggle', () => setAiModelActive({ model_code: model.model_code, is_active: !turningOff }), turningOff ? 'Đã tắt mô hình.' : 'Đã bật mô hình.');
  };

  // ─── Prompt ──────────────────────────────────────────────────
  const activatePrompt = async (version, isActive) => {
    const accepted = await confirm({
      title: isActive ? `Kích hoạt phiên bản ${version.version}` : `Tắt phiên bản ${version.version}`,
      description: isActive
        ? `Các lượt sinh câu hỏi dùng prompt "${version.name || version.template_key}" sau thời điểm này sẽ dùng phiên bản ${version.version}${runtime.prompt_source === 'db' ? '' : ' (chỉ có hiệu lực khi hệ thống đọc prompt từ cơ sở dữ liệu)'}.`
        : `Prompt "${version.name || version.template_key}" sẽ không có phiên bản nào đang dùng từ cơ sở dữ liệu.`,
      confirmLabel: isActive ? 'Kích hoạt' : 'Tắt',
      tone: isActive ? 'primary' : 'danger',
    });
    if (!accepted) return;
    await run('prompt-activate', () => activatePromptTemplate({ template_key: version.template_key, version: version.version, is_active: isActive }),
      isActive ? `Đã kích hoạt phiên bản ${version.version}.` : 'Đã tắt phiên bản.');
  };

  const savePrompt = async () => {
    const form = promptEditor;
    if (!form.template_key.trim() || !form.kind.trim() || !form.name.trim() || !form.prompt_body.trim()) {
      setPromptEditor((current) => ({ ...current, error: 'Nhập đủ mã, nhóm, tên và nội dung prompt.' }));
      return;
    }
    const accepted = await confirm({
      title: 'Lưu phiên bản prompt mới',
      description: 'Phiên bản mới được bật dùng ngay; phiên bản cũ vẫn giữ để rollback khi cần.',
      confirmLabel: 'Lưu và bật',
    });
    if (!accepted) return;
    setBusy('prompt');
    try {
      await savePromptTemplate({
        template_key: form.template_key.trim(),
        kind: form.kind.trim(),
        name: form.name.trim(),
        prompt_body: form.prompt_body,
        create_new_version: true,
        is_active: true,
      });
      setPromptKey(form.template_key.trim());
      setPromptEditor(null);
      showFlash('success', 'Đã lưu phiên bản prompt mới.');
      await load();
    } catch (err) {
      setPromptEditor((current) => ({ ...current, error: err.message || 'Lưu thất bại.' }));
    } finally {
      setBusy('');
    }
  };

  const previewPrompt = async () => {
    setBusy('preview');
    clearFlash();
    try {
      setPromptPreview(await testPromptTemplate({}));
    } catch (err) {
      showFlash('error', err.message || 'Không chạy thử được prompt.');
    } finally {
      setBusy('');
    }
  };

  const fromVersion = selectedGroup?.versions.find((item) => String(item.version) === compare.from);
  const toVersion = selectedGroup?.versions.find((item) => String(item.version) === compare.to);
  const promptDiff = fromVersion && toVersion && fromVersion !== toVersion
    ? diffLines(fromVersion.prompt_body, toVersion.prompt_body)
    : null;

  // ─── Tiêu chí ────────────────────────────────────────────────
  const weightSum = policyEditor
    ? Object.values(policyEditor.weights).reduce((sum, value) => sum + (Number(value) || 0), 0)
    : 0;

  const savePolicy = async () => {
    const weights = Object.fromEntries(Object.entries(policyEditor.weights).map(([key, value]) => [key, Number(value)]));
    const thresholds = Object.fromEntries(Object.entries(policyEditor.thresholds).map(([key, value]) => [key, Number(value)]));
    let error = '';
    if (!policyEditor.policy_name.trim()) error = 'Nhập tên bộ tiêu chí.';
    else if ([...Object.values(weights), ...Object.values(thresholds)].some((value) => !Number.isFinite(value) || value < 0 || value > 1)) error = 'Trọng số và ngưỡng phải là số từ 0 đến 1.';
    else if (Math.abs(weightSum - 1) > 0.01) error = `Tổng trọng số phải bằng 1 (hiện là ${weightSum.toFixed(2)}).`;
    else if (thresholds.yellow_min > thresholds.green_min) error = 'Ngưỡng "Cần xem lại" phải nhỏ hơn hoặc bằng ngưỡng "Đạt tốt".';
    if (error) {
      setPolicyEditor((current) => ({ ...current, error }));
      return;
    }
    const accepted = await confirm({
      title: 'Lưu và bật tiêu chí mới',
      description: 'Các lần AI đánh giá câu hỏi từ bây giờ sẽ dùng bộ tiêu chí này. Kết quả cũ không bị chấm lại.',
      confirmLabel: 'Lưu và bật',
    });
    if (!accepted) return;
    const ok = await run('policy', () => saveEvaluationPolicy({
      policy_name: policyEditor.policy_name.trim(),
      weights,
      thresholds,
      create_new_version: true,
      is_active: true,
    }), 'Đã bật phiên bản tiêu chí mới.');
    if (ok) setPolicyEditor(null);
  };

  const activatePolicy = async (policy) => {
    const accepted = await confirm({
      title: `Dùng lại phiên bản ${policy.version}`,
      description: 'Các lần AI đánh giá câu hỏi từ bây giờ sẽ dùng phiên bản này.',
      confirmLabel: 'Kích hoạt',
    });
    if (!accepted) return;
    await run('policy-activate', () => activateEvaluationPolicy({ policy_name: policy.policy_name, version: policy.version, is_active: true }),
      `Đã kích hoạt phiên bản ${policy.version}.`);
  };

  const renderApplied = () => (
    <section className="ws-card">
      <div className="ws-card-head">
        <div className="ws-card-title">
          <h2>Cấu hình đang áp dụng</h2>
          <span>Những gì hệ thống thực sự dùng lúc này cho từng luồng</span>
        </div>
      </div>
      <div className="ws-table-wrap">
        <table className="ws-table">
          <thead><tr><th>Luồng</th><th>Mô hình</th><th>Prompt</th><th>Tiêu chí</th></tr></thead>
          <tbody>
            <tr>
              <td><strong>Sinh câu hỏi</strong></td>
              <td className="ws-code">{runtime.generation_model_provider || '--'}</td>
              <td>{runtime.prompt_source === 'db' ? `${runtime.active_prompt_count ?? 0} prompt từ cơ sở dữ liệu` : 'Prompt trong mã nguồn'}</td>
              <td>--</td>
            </tr>
            <tr>
              <td><strong>Đánh giá câu hỏi</strong></td>
              <td className="ws-code">{runtime.evaluation_model_provider || '--'}</td>
              <td>Prompt đánh giá trong mã nguồn</td>
              <td>{runtime.active_evaluation_policy?.policy_name ? `${runtime.active_evaluation_policy.policy_name}, v${runtime.active_evaluation_policy.version}` : 'Mặc định'}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {(runtime.warnings || []).length > 0 && (
        <div style={{ display: 'grid', gap: 8, marginTop: 14 }}>
          {runtime.warnings.map((warning) => <Notice key={warning} tone="warn">{warning}</Notice>)}
        </div>
      )}
    </section>
  );

  return (
    <main className="ws-page ai-config-page">
      <WorkspaceHero
        badge="Quản trị viên"
        title="Cấu hình AI"
        description="Mô hình, mẫu prompt và tiêu chí điều khiển cách AI sinh và đánh giá câu hỏi."
        actions={(
          <button type="button" className="btn btn--outline" onClick={load} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            Làm mới
          </button>
        )}
      >
        <Tabs label="Nhóm cấu hình" value={tab} onChange={setTab} items={TABS.map((item) => ({
          ...item,
          count: item.value === 'models' ? models.length : item.value === 'prompts' ? promptGroups.length : policies.length,
        }))}
        />
      </WorkspaceHero>

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}
          {loading && !catalog ? (
            <div className="ws-card"><SkeletonRows rows={5} lines={2} /></div>
          ) : loadError ? (
            <div className="ws-card"><ErrorState message={loadError} onRetry={load} /></div>
          ) : (
            <>
              {renderApplied()}

              {tab === 'models' && (
                <section className="ws-card">
                  <div className="ws-card-head">
                    <div className="ws-card-title">
                      <h2>Mô hình</h2>
                      <span className="ws-list-count">{models.length} mô hình, {models.filter((model) => model.is_active !== false).length} đang bật</span>
                    </div>
                    <button type="button" className="btn btn--primary btn--sm" onClick={() => setModelDrawer({ isNew: true, form: JSON.parse(JSON.stringify(EMPTY_MODEL)), error: '' })}>
                      <FontAwesomeIcon icon={faPlus} />
                      Thêm mô hình
                    </button>
                  </div>
                  {models.length === 0 ? (
                    <EmptyState title="Chưa khai báo mô hình" description="Thêm mô hình Ollama hoặc Gemini để sinh và đánh giá câu hỏi." />
                  ) : (
                    <div className="ws-table-wrap">
                      <table className="ws-table">
                        <thead><tr><th>Mô hình</th><th>Nền tảng</th><th>Dùng cho</th><th>Kết nối</th><th>Trạng thái</th><th aria-label="Thao tác" /></tr></thead>
                        <tbody>
                          {models.map((model) => {
                            const health = healthOf(model);
                            return (
                              <tr key={model.model_code} style={{ opacity: model.is_active === false ? 0.65 : 1 }}>
                                <td>
                                  <strong>{model.display_name || model.model_name}</strong>
                                  <small className="ws-code">{model.model_code}</small>
                                </td>
                                <td>{model.runtime === 'GEMINI' ? 'Gemini' : 'Ollama'}<small>{model.model_name}</small></td>
                                <td>{(model.capabilities || []).map((item) => CAPABILITY_LABEL[item] || item).join(', ') || '--'}</td>
                                <td>
                                  <span className={`ws-pill ws-pill--${health.tone}`}>{health.text}</span>
                                  {model.last_health_check?.checked_at && <small>{formatDateTime(model.last_health_check.checked_at)}</small>}
                                </td>
                                <td>
                                  <span className={`ws-pill ${model.is_active === false ? 'ws-pill--outline' : 'ws-pill--success'}`}>{model.is_active === false ? 'Đã tắt' : 'Đang bật'}</span>
                                </td>
                                <td>
                                  <MoreMenu
                                    variant="icon"
                                    label={`Thao tác với ${model.display_name || model.model_code}`}
                                    items={[
                                      { key: 'check', label: busy === `health:${model.model_code}` ? 'Đang kiểm tra...' : 'Kiểm tra kết nối', icon: faHeartPulse, disabled: Boolean(busy), onClick: () => checkModel(model) },
                                      { key: 'edit', label: 'Sửa', icon: faPen, onClick: () => setModelDrawer({ isNew: false, form: modelToForm(model), error: '' }) },
                                      { key: 'toggle', label: model.is_active === false ? 'Bật' : 'Tắt', danger: model.is_active !== false, disabled: Boolean(busy), onClick: () => toggleModel(model) },
                                    ]}
                                  />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}

              {tab === 'prompts' && (
                <div className="ws-grid ws-grid--list">
                  <section className="ws-card">
                    <div className="ws-card-head" style={{ marginBottom: 12 }}>
                      <div className="ws-card-title">
                        <h2>Mẫu prompt</h2>
                        <span className="ws-list-count">{promptGroups.length} mẫu</span>
                      </div>
                      <button type="button" className="ws-icon-btn" aria-label="Thêm mẫu prompt" title="Thêm mẫu prompt" onClick={() => setPromptEditor({ isNew: true, template_key: '', kind: 'QUESTION_TYPE', name: '', prompt_body: '', error: '' })}>
                        <FontAwesomeIcon icon={faPlus} />
                      </button>
                    </div>
                    {promptGroups.length === 0 ? (
                      <EmptyState compact title="Chưa có mẫu prompt" description="Hệ thống đang dùng prompt trong mã nguồn." />
                    ) : (
                      <div className="ad-subject-list">
                        {promptGroups.map((group) => {
                          const active = group.versions.find((item) => item.is_active);
                          return (
                            <button type="button" key={group.key} className="ad-subject-item" aria-current={selectedGroup?.key === group.key} onClick={() => setPromptKey(group.key)}>
                              <b>{group.versions[0].name || group.key}</b>
                              <span>{group.versions.length} phiên bản, {active ? `đang dùng v${active.version}` : 'chưa bật'}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </section>

                  <section className="ws-card">
                    {!selectedGroup ? (
                      <EmptyState title="Chọn một mẫu prompt" description="Xem các phiên bản, so sánh khác biệt và kích hoạt hoặc rollback." />
                    ) : (
                      <>
                        <div className="ws-card-head">
                          <div className="ws-card-title">
                            <h2>{selectedGroup.versions[0].name || selectedGroup.key}</h2>
                            <span className="ws-code">{selectedGroup.key}</span>
                          </div>
                          <div className="ws-card-actions">
                            <button type="button" className="btn btn--outline btn--sm" onClick={previewPrompt} disabled={Boolean(busy)}>
                              {busy === 'preview' ? 'Đang chạy...' : 'Chạy thử'}
                            </button>
                            <button
                              type="button"
                              className="btn btn--primary btn--sm"
                              onClick={() => {
                                const base = selectedGroup.versions.find((item) => item.is_active) || selectedGroup.versions[0];
                                setPromptEditor({ isNew: false, template_key: base.template_key, kind: base.kind, name: base.name, prompt_body: base.prompt_body, error: '' });
                              }}
                            >
                              Tạo phiên bản mới
                            </button>
                          </div>
                        </div>
                        <div className="ws-table-wrap">
                          <table className="ws-table">
                            <thead><tr><th>Phiên bản</th><th>Tạo lúc</th><th>Trạng thái</th><th aria-label="Thao tác" /></tr></thead>
                            <tbody>
                              {selectedGroup.versions.map((version) => (
                                <tr key={version.version}>
                                  <td className="tabular"><strong>v{version.version}</strong></td>
                                  <td>{formatDateTime(version.created_at)}</td>
                                  <td>{version.is_active ? <span className="ws-pill ws-pill--success">Đang dùng</span> : <span className="ws-muted">Không dùng</span>}</td>
                                  <td>
                                    <button type="button" className="btn btn--ghost btn--sm" disabled={Boolean(busy)} onClick={() => activatePrompt(version, !version.is_active)}>
                                      {version.is_active ? 'Tắt' : 'Kích hoạt'}
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        {selectedGroup.versions.length > 1 && (
                          <>
                            <hr className="ws-divider" />
                            <div className="ws-toolbar" style={{ marginBottom: 10 }}>
                              <span className="ws-label">So sánh</span>
                              <select className="ws-select" style={{ width: 'auto' }} value={compare.from} onChange={(event) => setCompare({ ...compare, from: event.target.value })} aria-label="Phiên bản gốc">
                                {selectedGroup.versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}
                              </select>
                              <span className="ws-muted">với</span>
                              <select className="ws-select" style={{ width: 'auto' }} value={compare.to} onChange={(event) => setCompare({ ...compare, to: event.target.value })} aria-label="Phiên bản so sánh">
                                {selectedGroup.versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}
                              </select>
                            </div>
                            {promptDiff ? (
                              <pre className="ad-diff">
                                {promptDiff.map((line, index) => (
                                  <span key={index} className={`ad-diff__${line.type}`}>
                                    {line.type === 'add' ? '+ ' : line.type === 'remove' ? '- ' : '  '}
                                    {line.text}
                                    {'\n'}
                                  </span>
                                ))}
                              </pre>
                            ) : (
                              <p className="ws-hint">Chọn hai phiên bản khác nhau để xem khác biệt.</p>
                            )}
                          </>
                        )}

                        {promptPreview && (
                          <>
                            <hr className="ws-divider" />
                            <h4 className="ws-subhead">Kết quả chạy thử ({promptPreview.length} ký tự, nguồn {promptPreview.prompt_source === 'db' ? 'cơ sở dữ liệu' : 'mã nguồn'})</h4>
                            <pre className="ws-pre" style={{ maxHeight: 360 }}>{promptPreview.rendered_prompt}</pre>
                          </>
                        )}
                      </>
                    )}
                  </section>
                </div>
              )}

              {tab === 'policies' && (
                <section className="ws-card">
                  <div className="ws-card-head">
                    <div className="ws-card-title">
                      <h2>Tiêu chí đánh giá</h2>
                      <span>Trọng số 5 tiêu chí và các ngưỡng quyết định màu chất lượng, đề xuất đạt</span>
                    </div>
                    <button type="button" className="btn btn--primary btn--sm" onClick={() => setPolicyEditor({ ...policyForm(activePolicy), error: '' })}>
                      <FontAwesomeIcon icon={faPlus} />
                      Tạo phiên bản mới
                    </button>
                  </div>
                  {policies.length === 0 ? (
                    <EmptyState compact title="Chưa có bộ tiêu chí" description="Hệ thống đang dùng trọng số mặc định." />
                  ) : (
                    <div className="ws-table-wrap">
                      <table className="ws-table">
                        <thead>
                          <tr>
                            <th>Phiên bản</th>
                            {REVIEW_CRITERIA.map((criterion) => <th key={criterion.key} className="ws-num">{criterion.label}</th>)}
                            <th className="ws-num">Điểm đạt</th>
                            <th>Trạng thái</th>
                            <th aria-label="Thao tác" />
                          </tr>
                        </thead>
                        <tbody>
                          {policies.map((policy) => (
                            <tr key={`${policy.policy_name}-${policy.version}`}>
                              <td><strong>v{policy.version}</strong><small>{policy.policy_name}</small></td>
                              {REVIEW_CRITERIA.map((criterion) => (
                                <td key={criterion.key} className="ws-num">{Math.round(Number(policy.weights?.[criterion.key] ?? DEFAULT_WEIGHTS[criterion.key]) * 100)}%</td>
                              ))}
                              <td className="ws-num">{policy.thresholds?.pass_min ?? DEFAULT_THRESHOLDS.pass_min}</td>
                              <td>{policy.is_active ? <span className="ws-pill ws-pill--success">Đang dùng</span> : <span className="ws-muted">Không dùng</span>}</td>
                              <td>
                                <MoreMenu
                                  variant="icon"
                                  label={`Thao tác với phiên bản ${policy.version}`}
                                  items={[
                                    { key: 'copy', label: 'Sao chép để sửa', icon: faPen, onClick: () => setPolicyEditor({ ...policyForm(policy), error: '' }) },
                                    { key: 'activate', label: 'Kích hoạt', disabled: policy.is_active || Boolean(busy), title: policy.is_active ? 'Phiên bản này đang được dùng' : undefined, onClick: () => activatePolicy(policy) },
                                  ]}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </section>

      <Drawer
        open={Boolean(modelDrawer)}
        wide
        title={modelDrawer?.isNew ? 'Thêm mô hình' : 'Sửa mô hình'}
        subtitle={modelDrawer?.isNew ? undefined : modelDrawer?.form.model_code}
        onClose={() => setModelDrawer(null)}
        busy={busy === 'model'}
        as="form"
        onSubmit={saveModel}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setModelDrawer(null)} disabled={busy === 'model'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busy === 'model'}>{busy === 'model' ? 'Đang lưu...' : 'Lưu mô hình'}</button>
          </>
        )}
      >
        {modelDrawer && (
          <>
            <div className="ws-form-grid">
              <label className="ws-field"><span>Tên hiển thị</span><input className="ws-input" value={modelDrawer.form.display_name} onChange={(event) => updateModel({ display_name: event.target.value })} placeholder="Qwen3 (8B)" /></label>
              <label className="ws-field">
                <span>Mã cấu hình</span>
                <input className="ws-input" value={modelDrawer.form.model_code} disabled={!modelDrawer.isNew} onChange={(event) => updateModel({ model_code: event.target.value })} placeholder="qwen3-8b" />
              </label>
              <label className="ws-field"><span>Tên mô hình trên nền tảng</span><input className="ws-input" value={modelDrawer.form.model_name} onChange={(event) => updateModel({ model_name: event.target.value })} placeholder="qwen3:8b" /></label>
              <label className="ws-field">
                <span>Nền tảng</span>
                <select className="ws-select" value={modelDrawer.form.runtime} onChange={(event) => updateModel({ runtime: event.target.value })}>
                  <option value="OLLAMA">Ollama (chạy nội bộ)</option>
                  <option value="GEMINI">Gemini</option>
                </select>
              </label>
              <label className="ws-field ws-span-2"><span>Mô tả ngắn</span><input className="ws-input" value={modelDrawer.form.description} onChange={(event) => updateModel({ description: event.target.value })} placeholder="Khi nào nên chọn mô hình này?" /></label>
            </div>
            <div className="ws-field">
              <span className="ws-label">Dùng cho</span>
              <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
                {Object.entries(CAPABILITY_LABEL).map(([value, label]) => (
                  <label className="ws-check" key={value}>
                    <input
                      type="checkbox"
                      checked={modelDrawer.form.capabilities.includes(value)}
                      onChange={() => updateModel({
                        capabilities: modelDrawer.form.capabilities.includes(value)
                          ? modelDrawer.form.capabilities.filter((item) => item !== value)
                          : [...modelDrawer.form.capabilities, value],
                      })}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
            <div className="ws-form-grid">
              <label className="ws-field"><span>Thời gian chờ (giây)</span><input className="ws-input" type="number" min="1" max="1800" value={modelDrawer.form.config.timeout_seconds} onChange={(event) => updateModelConfig({ timeout_seconds: event.target.value })} /></label>
              <label className="ws-field"><span>Độ sáng tạo (0 đến 2)</span><input className="ws-input" type="number" min="0" max="2" step="0.1" value={modelDrawer.form.config.temperature} onChange={(event) => updateModelConfig({ temperature: event.target.value })} /></label>
              {modelDrawer.form.runtime === 'OLLAMA' ? (
                <>
                  <label className="ws-field"><span>Số token tối đa</span><input className="ws-input" type="number" min="1" max="32768" value={modelDrawer.form.config.num_predict} onChange={(event) => updateModelConfig({ num_predict: event.target.value })} /></label>
                  <label className="ws-field"><span>Địa chỉ Ollama</span><input className="ws-input" value={modelDrawer.form.config.endpoint} onChange={(event) => updateModelConfig({ endpoint: event.target.value })} placeholder="Để trống để dùng mặc định" /></label>
                </>
              ) : (
                <label className="ws-field"><span>Số token tối đa</span><input className="ws-input" type="number" min="1" max="65536" value={modelDrawer.form.config.max_output_tokens} onChange={(event) => updateModelConfig({ max_output_tokens: event.target.value })} /></label>
              )}
              <label className="ws-field"><span>Thứ tự hiển thị</span><input className="ws-input" type="number" min="0" value={modelDrawer.form.priority} onChange={(event) => updateModel({ priority: event.target.value })} /></label>
            </div>
            <label className="ws-check"><input type="checkbox" checked={modelDrawer.form.is_active} onChange={(event) => updateModel({ is_active: event.target.checked })} />Đang bật</label>
            {modelDrawer.error && <Notice tone="error">{modelDrawer.error}</Notice>}
          </>
        )}
      </Drawer>

      <Drawer
        open={Boolean(promptEditor)}
        wide
        title={promptEditor?.isNew ? 'Thêm mẫu prompt' : 'Phiên bản prompt mới'}
        subtitle={promptEditor?.isNew ? undefined : promptEditor?.template_key}
        onClose={() => setPromptEditor(null)}
        busy={busy === 'prompt'}
        as="form"
        onSubmit={savePrompt}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setPromptEditor(null)} disabled={busy === 'prompt'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busy === 'prompt'}>{busy === 'prompt' ? 'Đang lưu...' : 'Lưu phiên bản'}</button>
          </>
        )}
      >
        {promptEditor && (
          <>
            <div className="ws-form-grid">
              <label className="ws-field"><span>Mã prompt</span><input className="ws-input" value={promptEditor.template_key} disabled={!promptEditor.isNew} onChange={(event) => setPromptEditor({ ...promptEditor, template_key: event.target.value, error: '' })} /></label>
              <label className="ws-field"><span>Nhóm</span><input className="ws-input" value={promptEditor.kind} onChange={(event) => setPromptEditor({ ...promptEditor, kind: event.target.value, error: '' })} /></label>
              <label className="ws-field ws-span-2"><span>Tên hiển thị</span><input className="ws-input" value={promptEditor.name} onChange={(event) => setPromptEditor({ ...promptEditor, name: event.target.value, error: '' })} /></label>
            </div>
            <label className="ws-field">
              <span>Nội dung</span>
              <textarea className="ws-textarea ad-code-editor" style={{ minHeight: 360 }} value={promptEditor.prompt_body} onChange={(event) => setPromptEditor({ ...promptEditor, prompt_body: event.target.value, error: '' })} />
            </label>
            {promptEditor.error && <Notice tone="error">{promptEditor.error}</Notice>}
          </>
        )}
      </Drawer>

      <Drawer
        open={Boolean(policyEditor)}
        title="Phiên bản tiêu chí mới"
        onClose={() => setPolicyEditor(null)}
        busy={busy === 'policy'}
        as="form"
        onSubmit={savePolicy}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setPolicyEditor(null)} disabled={busy === 'policy'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busy === 'policy'}>{busy === 'policy' ? 'Đang lưu...' : 'Lưu và bật'}</button>
          </>
        )}
      >
        {policyEditor && (
          <>
            <label className="ws-field"><span>Tên bộ tiêu chí</span><input className="ws-input" value={policyEditor.policy_name} onChange={(event) => setPolicyEditor({ ...policyEditor, policy_name: event.target.value, error: '' })} /></label>
            <div className="ws-between">
              <span className="ws-label">Trọng số</span>
              <span className={`ws-pill ${Math.abs(weightSum - 1) > 0.01 ? 'ws-pill--danger' : 'ws-pill--success'} tabular`}>Tổng {weightSum.toFixed(2)}</span>
            </div>
            <div className="ad-weights">
              {Object.keys(policyEditor.weights).map((key) => (
                <label className="ws-field" key={key}>
                  <span>{criterionLabel(key)}</span>
                  <input className="ws-input" type="number" min="0" max="1" step="0.05" value={policyEditor.weights[key]} onChange={(event) => setPolicyEditor({ ...policyEditor, error: '', weights: { ...policyEditor.weights, [key]: event.target.value } })} />
                </label>
              ))}
            </div>
            <span className="ws-label">Ngưỡng</span>
            {THRESHOLD_FIELDS.map((field) => (
              <label className="ws-field" key={field.key}>
                <span>{field.label}</span>
                <input className="ws-input" type="number" min="0" max="1" step="0.05" value={policyEditor.thresholds[field.key] ?? ''} onChange={(event) => setPolicyEditor({ ...policyEditor, error: '', thresholds: { ...policyEditor.thresholds, [field.key]: event.target.value } })} />
                <small>{field.hint}</small>
              </label>
            ))}
            {policyEditor.error && <Notice tone="error">{policyEditor.error}</Notice>}
          </>
        )}
      </Drawer>
      {confirmDialog}
    </main>
  );
}

export default AiConfigPage;
