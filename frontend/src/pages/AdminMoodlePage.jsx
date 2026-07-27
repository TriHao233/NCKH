import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBan,
  faCheckCircle,
  faCircleExclamation,
  faFloppyDisk,
  faPlug,
  faRotateRight,
  faSearch,
} from '@fortawesome/free-solid-svg-icons';
import {
  checkMoodleTarget,
  deactivateMoodleTarget,
  listMoodlePublications,
  listMoodleTargets,
  retryMoodlePublication,
  saveMoodleTarget,
} from '../api/adminMoodle';
import '../css/AdminMoodlePage.css';

const emptyForm = {
  site_key: 'demo-moodle',
  site_name: 'Demo Moodle',
  mode: 'MOCK',
  base_url: '',
  token_env_var: '',
  default_course_id: 'ctdl-demo',
  default_category_id: 'qbank-demo',
  allowed_roles: ['Admin', 'Reviewer'],
  is_active: true,
};

const PUBLISH_ROLES = [
  { value: 'Admin', label: 'Quản trị viên' },
  { value: 'Reviewer', label: 'Người duyệt' },
];

const STATUS_LABEL = {
  all: 'Tất cả trạng thái',
  PUBLISHED: 'Đã ghi nhận',
  FAILED: 'Lỗi',
  QUEUED: 'Đang chờ',
  PROCESSING: 'Đang xử lý',
};

function formatDateTime(value) {
  if (!value) return 'Chưa có';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Chưa có';
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

function checkText(target) {
  const check = target?.last_check;
  if (!check) return 'Chưa kiểm tra';
  return check.ok ? 'Kết nối ổn' : 'Cần xử lý';
}

function publicationStatusClass(status) {
  if (status === 'PUBLISHED') return 'success';
  if (status === 'FAILED') return 'danger';
  if (['QUEUED', 'PROCESSING'].includes(status)) return 'active';
  return 'muted';
}

function formFromTarget(target = {}) {
  return {
    ...emptyForm,
    ...target,
    allowed_roles: target.allowed_roles?.length ? target.allowed_roles : emptyForm.allowed_roles,
  };
}

function AdminMoodlePage() {
  const [targets, setTargets] = useState([]);
  const [publications, setPublications] = useState([]);
  const [publicationSummary, setPublicationSummary] = useState({ total: 0, published: 0, simulated: 0, failed: 0, pending: 0 });
  const [publicationTotal, setPublicationTotal] = useState(0);
  const [form, setForm] = useState(emptyForm);
  const [selectedKey, setSelectedKey] = useState('');
  const [publicationStatus, setPublicationStatus] = useState('all');
  const [siteFilter, setSiteFilter] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [publicationsLoading, setPublicationsLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [checkingKey, setCheckingKey] = useState('');
  const [retryingId, setRetryingId] = useState('');

  useEffect(() => {
    const handle = setTimeout(() => setSearchTerm(searchInput.trim()), 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const loadTargets = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listMoodleTargets();
      const items = result.items || [];
      setTargets(items);
      if (!selectedKey && items[0]) {
        setSelectedKey(items[0].site_key);
        setForm(formFromTarget(items[0]));
      }
    } catch (err) {
      setError(err.message || 'Không tải được Moodle target');
    } finally {
      setLoading(false);
    }
  }, [selectedKey]);

  const loadPublications = useCallback(async () => {
    setPublicationsLoading(true);
    try {
      const result = await listMoodlePublications({
        page: 1,
        pageSize: 50,
        status: publicationStatus,
        siteKey: siteFilter,
        search: searchTerm,
      });
      setPublications(result.items || []);
      setPublicationSummary(result.summary || { total: 0, published: 0, simulated: 0, failed: 0, pending: 0 });
      setPublicationTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được publication Moodle');
      setPublications([]);
      setPublicationTotal(0);
    } finally {
      setPublicationsLoading(false);
    }
  }, [publicationStatus, searchTerm, siteFilter]);

  useEffect(() => {
    loadTargets();
  }, [loadTargets]);

  useEffect(() => {
    loadPublications();
  }, [loadPublications]);

  const selectedTarget = useMemo(
    () => targets.find((target) => target.site_key === selectedKey) || null,
    [selectedKey, targets],
  );

  const pickTarget = (target) => {
    setSelectedKey(target.site_key);
    setForm(formFromTarget(target));
  };

  const newTarget = () => {
    setSelectedKey('');
    setForm(formFromTarget());
  };

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const toggleAllowedRole = (role) => {
    setForm((current) => {
      const currentRoles = current.allowed_roles?.length ? current.allowed_roles : emptyForm.allowed_roles;
      const nextSet = new Set(currentRoles);
      if (nextSet.has(role) && nextSet.size > 1) {
        nextSet.delete(role);
      } else {
        nextSet.add(role);
      }
      return {
        ...current,
        allowed_roles: PUBLISH_ROLES
          .map((item) => item.value)
          .filter((item) => nextSet.has(item)),
      };
    });
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const saved = await saveMoodleTarget({
        ...form,
        allowed_roles: form.allowed_roles?.length ? form.allowed_roles : ['Admin'],
      });
      setSelectedKey(saved.site_key);
      setForm(formFromTarget(saved));
      await loadTargets();
    } catch (err) {
      setError(err.message || 'Lưu Moodle target thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleCheck = async (target) => {
    setCheckingKey(target.site_key);
    setError('');
    try {
      const result = await checkMoodleTarget(target.site_key);
      setForm((current) => (
        current.site_key === target.site_key ? { ...current, last_check: result.check } : current
      ));
      await loadTargets();
    } catch (err) {
      setError(err.message || 'Kiểm tra Moodle target thất bại');
    } finally {
      setCheckingKey('');
    }
  };

  const handleDeactivate = async (target) => {
    if (!window.confirm(`Khóa Moodle target "${target.site_name}"?`)) return;
    setSaving(true);
    setError('');
    try {
      await deactivateMoodleTarget(target.site_key);
      await loadTargets();
    } catch (err) {
      setError(err.message || 'Khóa Moodle target thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleRetryPublication = async (item) => {
    if (!window.confirm(`Retry Moodle publication cho "${item.question_code || item.question_id}"?`)) return;
    setRetryingId(item.id);
    setError('');
    try {
      await retryMoodlePublication(item.id);
      await loadPublications();
    } catch (err) {
      setError(err.message || 'Retry publication Moodle thất bại');
    } finally {
      setRetryingId('');
    }
  };

  return (
    <main className="admin-moodle-page">
      <section className="moodle-header">
        <div>
          <span>Quản trị hệ thống</span>
          <h1>Moodle target</h1>
          <p>Quản lý site, course, category và theo dõi publication Moodle theo mode MOCK hoặc REST API.</p>
        </div>
        <button type="button" className="moodle-primary-button" onClick={() => { loadTargets(); loadPublications(); }} disabled={loading || publicationsLoading}>
          <FontAwesomeIcon icon={faRotateRight} />
          <span>Làm mới</span>
        </button>
      </section>

      <section className="moodle-summary">
        <button type="button" onClick={() => setPublicationStatus('all')}>
          <b>{publicationSummary.total}</b>
          <span>Tổng publication</span>
        </button>
        <button type="button" onClick={() => setPublicationStatus('PUBLISHED')}>
          <b>{publicationSummary.published}</b>
          <span>{publicationSummary.simulated || 0} mô phỏng</span>
        </button>
        <button type="button" className="summary-danger" onClick={() => setPublicationStatus('FAILED')}>
          <b>{publicationSummary.failed}</b>
          <span>Dead-letter</span>
        </button>
        <button type="button" onClick={() => setPublicationStatus('PROCESSING')}>
          <b>{publicationSummary.pending}</b>
          <span>Đang xử lý</span>
        </button>
      </section>

      {error && <p className="moodle-error">{error}</p>}

      <section className="moodle-layout">
        <div className="moodle-target-panel">
          <div className="panel-heading">
            <div>
              <h2>Targets</h2>
              <span>{targets.length} cấu hình</span>
            </div>
            <button type="button" onClick={newTarget}>Tạo mới</button>
          </div>

          {loading ? (
            <p className="moodle-empty">Đang tải target...</p>
          ) : (
            <div className="target-list">
              {targets.map((target) => (
                <article
                  key={target.site_key}
                  className={`target-row ${selectedKey === target.site_key ? 'target-row--active' : ''}`}
                  onClick={() => pickTarget(target)}
                >
                  <div className="target-main">
                    <div>
                      <strong>{target.site_name}</strong>
                      <small>{target.site_key} · {target.default_course_id}/{target.default_category_id}</small>
                    </div>
                    <span className={`target-check ${target.last_check?.ok ? 'target-check--ok' : ''}`}>
                      {checkText(target)}
                    </span>
                  </div>
                  <div className="target-meta">
                    <span>{target.mode}</span>
                    <span>{target.is_active ? 'Active' : 'Locked'}</span>
                    <span>{(target.allowed_roles?.length ? target.allowed_roles : emptyForm.allowed_roles).join(', ')}</span>
                    <span>{formatDateTime(target.last_check?.checked_at)}</span>
                  </div>
                  <div className="target-actions">
                    <button
                      type="button"
                      title="Kiểm tra kết nối"
                      disabled={checkingKey === target.site_key}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleCheck(target);
                      }}
                    >
                      <FontAwesomeIcon icon={faPlug} />
                    </button>
                    <button
                      type="button"
                      title="Khóa target"
                      disabled={!target.is_active || saving}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDeactivate(target);
                      }}
                    >
                      <FontAwesomeIcon icon={faBan} />
                    </button>
                  </div>
                </article>
              ))}
              {targets.length === 0 && <p className="moodle-empty">Chưa có Moodle target.</p>}
            </div>
          )}
        </div>

        <form className="moodle-form-panel" onSubmit={handleSave}>
          <div className="panel-heading">
            <div>
              <h2>{selectedTarget ? 'Cập nhật target' : 'Tạo target'}</h2>
              <span>{selectedTarget?.last_check?.message || 'Credential thật chỉ lưu qua biến môi trường'}</span>
            </div>
          </div>
          <div className="form-grid">
            <label>
              Site key
              <input value={form.site_key} onChange={(event) => updateForm('site_key', event.target.value)} />
            </label>
            <label>
              Tên site
              <input value={form.site_name} onChange={(event) => updateForm('site_name', event.target.value)} />
            </label>
            <label>
              Mode
              <select value={form.mode} onChange={(event) => updateForm('mode', event.target.value)}>
                <option value="MOCK">MOCK</option>
                <option value="REST_API">REST_API</option>
              </select>
            </label>
            <label>
              Active
              <select value={form.is_active ? 'true' : 'false'} onChange={(event) => updateForm('is_active', event.target.value === 'true')}>
                <option value="true">Active</option>
                <option value="false">Locked</option>
              </select>
            </label>
            <label className="form-span">
              Base URL
              <input value={form.base_url || ''} onChange={(event) => updateForm('base_url', event.target.value)} placeholder="https://moodle.example.edu" />
            </label>
            <label>
              Token env var
              <input value={form.token_env_var || ''} onChange={(event) => updateForm('token_env_var', event.target.value)} placeholder="MOODLE_API_TOKEN" />
            </label>
            <label>
              Course ID
              <input value={form.default_course_id} onChange={(event) => updateForm('default_course_id', event.target.value)} />
            </label>
            <label>
              Category ID
              <input value={form.default_category_id} onChange={(event) => updateForm('default_category_id', event.target.value)} />
            </label>
            <div className="form-span role-toggle-group">
              <span>Được publish</span>
              <div>
                {PUBLISH_ROLES.map((role) => (
                  <label key={role.value}>
                    <input
                      type="checkbox"
                      checked={(form.allowed_roles || emptyForm.allowed_roles).includes(role.value)}
                      onChange={() => toggleAllowedRole(role.value)}
                    />
                    {role.label}
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="form-actions">
            {selectedTarget?.last_check && (
              <span className={selectedTarget.last_check.ok ? 'check-ok' : 'check-fail'}>
                <FontAwesomeIcon icon={selectedTarget.last_check.ok ? faCheckCircle : faCircleExclamation} />
                {selectedTarget.last_check.message}
              </span>
            )}
            <button type="submit" disabled={saving}>
              <FontAwesomeIcon icon={faFloppyDisk} />
              <span>{saving ? 'Đang lưu' : 'Lưu target'}</span>
            </button>
          </div>
        </form>
      </section>

      <section className="publication-panel">
        <div className="panel-heading">
          <div>
            <h2>Publication / dead-letter</h2>
            <span>{publicationTotal} kết quả</span>
          </div>
          <div className="publication-filters">
            <select value={siteFilter} onChange={(event) => setSiteFilter(event.target.value)}>
              <option value="all">Tất cả site</option>
              {targets.map((target) => (
                <option key={target.site_key} value={target.site_key}>{target.site_name}</option>
              ))}
            </select>
            <select value={publicationStatus} onChange={(event) => setPublicationStatus(event.target.value)}>
              {Object.entries(STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <label>
              <FontAwesomeIcon icon={faSearch} />
              <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Mã câu hỏi, ref, ghi chú..." />
            </label>
          </div>
        </div>

        <div className="publication-table-wrap">
          <table className="publication-table">
            <thead>
              <tr>
                <th>Question</th>
                <th>Target</th>
                <th>Trạng thái</th>
                <th>Ref</th>
                <th>Export</th>
                <th>Thời gian</th>
                <th>Ghi chú</th>
                <th>Retry</th>
              </tr>
            </thead>
            <tbody>
              {publications.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.question_code || item.question_id}</strong>
                    <small>Version {item.question_version}</small>
                  </td>
                  <td>
                    <span>{item.target?.site_name || item.target?.moodle_site_id || 'Target'}</span>
                    <small>{item.publication_mode || item.target?.mode || 'MOCK'} · {item.target?.course_id}/{item.target?.category_id}</small>
                  </td>
                  <td>
                    <span className={`publication-status publication-status--${publicationStatusClass(item.status)}`}>
                      {item.status_label || STATUS_LABEL[item.status] || item.status || 'Chưa rõ'}
                    </span>
                  </td>
                  <td>
                    <span>{item.moodle_question_ref_id || 'Chưa có'}</span>
                    {item.publication_mode === 'MOCK' && <small>Mock local, không phải Moodle ID thật</small>}
                  </td>
                  <td>{item.export_formats?.length ? item.export_formats.join(', ') : item.export_format}</td>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td className="publication-error">{item.error_message || item.message || (item.external_sync === false ? 'Ghi nhận cục bộ' : 'Không có')}</td>
                  <td>
                    {item.status === 'FAILED' ? (
                      <button
                        type="button"
                        className="publication-retry-button"
                        title="Retry publication lỗi"
                        disabled={retryingId === item.id}
                        onClick={() => handleRetryPublication(item)}
                      >
                        <FontAwesomeIcon icon={faRotateRight} />
                      </button>
                    ) : (
                      <span className="publication-no-action">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {publicationsLoading && <p className="moodle-empty">Đang tải publication...</p>}
          {!publicationsLoading && publications.length === 0 && <p className="moodle-empty">Không có publication phù hợp.</p>}
        </div>
      </section>
    </main>
  );
}

export default AdminMoodlePage;
