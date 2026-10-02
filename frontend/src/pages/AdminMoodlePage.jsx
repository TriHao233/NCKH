import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBan,
  faCheckCircle,
  faCircleExclamation,
  faFloppyDisk,
  faPen,
  faPlug,
  faPlus,
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
  site_key: '',
  site_name: '',
  mode: 'MOCK',
  base_url: '',
  token_env_var: '',
  default_course_id: '',
  default_category_id: '',
  allowed_roles: ['Admin', 'Reviewer'],
  is_active: true,
};

const PUBLISH_ROLES = [
  { value: 'Admin', label: 'Quản trị viên' },
  { value: 'Reviewer', label: 'Người duyệt' },
];
const ROLE_LABEL = Object.fromEntries(PUBLISH_ROLES.map((role) => [role.value, role.label]));
const MODE_LABEL = { MOCK: 'Mô phỏng', REST_API: 'Moodle thật' };

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
  if (!check) return 'Chưa kiểm tra kết nối';
  return check.ok ? 'Kết nối ổn' : 'Kết nối có vấn đề';
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
  const [editingKey, setEditingKey] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [formError, setFormError] = useState('');
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
      setTargets(result.items || []);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách kết nối Moodle');
    } finally {
      setLoading(false);
    }
  }, []);

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
      setError(err.message || 'Không tải được các lượt đưa lên Moodle');
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

  const editingTarget = useMemo(
    () => targets.find((target) => target.site_key === editingKey) || null,
    [editingKey, targets],
  );

  const openForm = (target) => {
    setEditingKey(target?.site_key || '');
    setForm(formFromTarget(target || {}));
    setFormError('');
    setFormOpen(true);
  };

  const closeForm = () => {
    if (!saving) setFormOpen(false);
  };

  useEffect(() => {
    if (!formOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !saving) setFormOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [formOpen, saving]);

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
    setFormError('');
    try {
      await saveMoodleTarget({
        ...form,
        allowed_roles: form.allowed_roles?.length ? form.allowed_roles : ['Admin'],
      });
      setFormOpen(false);
      await loadTargets();
    } catch (err) {
      setFormError(err.message || 'Lưu kết nối Moodle thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleCheck = async (target) => {
    setCheckingKey(target.site_key);
    setError('');
    try {
      await checkMoodleTarget(target.site_key);
      await loadTargets();
    } catch (err) {
      setError(err.message || 'Kiểm tra kết nối Moodle thất bại');
    } finally {
      setCheckingKey('');
    }
  };

  const handleDeactivate = async (target) => {
    if (!window.confirm(`Khóa kết nối "${target.site_name}"? Người dùng sẽ không đưa được câu hỏi lên qua kết nối này.`)) return;
    setSaving(true);
    setError('');
    try {
      await deactivateMoodleTarget(target.site_key);
      await loadTargets();
    } catch (err) {
      setError(err.message || 'Khóa kết nối Moodle thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleRetryPublication = async (item) => {
    if (!window.confirm(`Chạy lại lượt đưa "${item.question_code || item.question_id}" lên Moodle?`)) return;
    setRetryingId(item.id);
    setError('');
    try {
      await retryMoodlePublication(item.id);
      await loadPublications();
    } catch (err) {
      setError(err.message || 'Chạy lại lượt đưa lên Moodle thất bại');
    } finally {
      setRetryingId('');
    }
  };

  return (
    <main className="admin-moodle-page">
      <section className="moodle-header">
        <div>
          <span>Hệ thống</span>
          <h1>Moodle</h1>
          <p>Quản lý các kết nối tới Moodle và theo dõi những lượt đưa câu hỏi lên.</p>
        </div>
        <button type="button" className="moodle-secondary-button" onClick={() => { loadTargets(); loadPublications(); }} disabled={loading || publicationsLoading}>
          <FontAwesomeIcon icon={faRotateRight} />
          <span>Làm mới</span>
        </button>
      </section>

      <section className="moodle-summary" aria-label="Số lượt đưa lên theo trạng thái">
        <button type="button" className={publicationStatus === 'all' ? 'is-active' : ''} onClick={() => setPublicationStatus('all')}>
          <b>{publicationSummary.total}</b>
          <span>Tổng lượt đưa lên</span>
        </button>
        <button type="button" className={publicationStatus === 'PUBLISHED' ? 'is-active' : ''} onClick={() => setPublicationStatus('PUBLISHED')}>
          <b>{publicationSummary.published}</b>
          <span>Đã ghi nhận · {publicationSummary.simulated || 0} mô phỏng</span>
        </button>
        <button type="button" className={`summary-danger ${publicationStatus === 'FAILED' ? 'is-active' : ''}`} onClick={() => setPublicationStatus('FAILED')}>
          <b>{publicationSummary.failed}</b>
          <span>Lỗi, cần chạy lại</span>
        </button>
        <button type="button" className={publicationStatus === 'PROCESSING' ? 'is-active' : ''} onClick={() => setPublicationStatus('PROCESSING')}>
          <b>{publicationSummary.pending}</b>
          <span>Đang xử lý</span>
        </button>
      </section>

      {error && <p className="moodle-error" role="alert">{error}</p>}

      <section className="moodle-panel">
        <div className="moodle-panel-heading">
          <div>
            <h2>Kết nối Moodle</h2>
            <p>{targets.length} kết nối · mỗi kết nối trỏ tới một khoá học và danh mục câu hỏi trên Moodle.</p>
          </div>
          <button type="button" className="moodle-primary-button" onClick={() => openForm(null)}>
            <FontAwesomeIcon icon={faPlus} />
            <span>Thêm kết nối</span>
          </button>
        </div>

        {loading ? (
          <p className="moodle-empty">Đang tải kết nối...</p>
        ) : (
          <div className="target-list">
            {targets.map((target) => (
              <article key={target.site_key} className={`target-row ${target.is_active ? '' : 'target-row--locked'}`}>
                <div className="target-main">
                  <strong>{target.site_name}</strong>
                  <small>
                    Mã {target.site_key} · khoá học {target.default_course_id || '--'} · danh mục {target.default_category_id || '--'}
                  </small>
                  <div className="target-meta">
                    <span>{MODE_LABEL[target.mode] || target.mode}</span>
                    <span className={target.is_active ? '' : 'target-meta--locked'}>{target.is_active ? 'Đang dùng' : 'Đã khóa'}</span>
                    <span>
                      Được đưa lên: {(target.allowed_roles?.length ? target.allowed_roles : emptyForm.allowed_roles).map((role) => ROLE_LABEL[role] || role).join(', ')}
                    </span>
                  </div>
                  <small className={`target-check ${target.last_check?.ok ? 'target-check--ok' : ''}`}>
                    {checkText(target)}
                    {target.last_check?.checked_at ? ` · ${formatDateTime(target.last_check.checked_at)}` : ''}
                    {target.last_check?.message && !target.last_check.ok ? ` · ${target.last_check.message}` : ''}
                  </small>
                </div>
                <div className="target-actions">
                  <button type="button" disabled={checkingKey === target.site_key} onClick={() => handleCheck(target)}>
                    <FontAwesomeIcon icon={faPlug} />
                    <span>{checkingKey === target.site_key ? 'Đang kiểm tra' : 'Kiểm tra'}</span>
                  </button>
                  <button type="button" onClick={() => openForm(target)}>
                    <FontAwesomeIcon icon={faPen} />
                    <span>Sửa</span>
                  </button>
                  <button type="button" disabled={!target.is_active || saving} onClick={() => handleDeactivate(target)}>
                    <FontAwesomeIcon icon={faBan} />
                    <span>Khóa</span>
                  </button>
                </div>
              </article>
            ))}
            {targets.length === 0 && <p className="moodle-empty">Chưa có kết nối Moodle nào.</p>}
          </div>
        )}
      </section>

      <section className="moodle-panel">
        <div className="moodle-panel-heading">
          <div>
            <h2>Các lượt đưa câu hỏi lên Moodle</h2>
            <p>{publicationTotal} kết quả</p>
          </div>
          <div className="publication-filters">
            <select aria-label="Lọc theo kết nối" value={siteFilter} onChange={(event) => setSiteFilter(event.target.value)}>
              <option value="all">Tất cả kết nối</option>
              {targets.map((target) => (
                <option key={target.site_key} value={target.site_key}>{target.site_name}</option>
              ))}
            </select>
            <select aria-label="Lọc theo trạng thái" value={publicationStatus} onChange={(event) => setPublicationStatus(event.target.value)}>
              {Object.entries(STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <label>
              <FontAwesomeIcon icon={faSearch} />
              <input aria-label="Tìm lượt đưa lên" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Mã câu hỏi, mã trên Moodle, ghi chú..." />
            </label>
          </div>
        </div>

        <div className="publication-table-wrap">
          <table className="publication-table">
            <thead>
              <tr>
                <th>Câu hỏi</th>
                <th>Kết nối</th>
                <th>Trạng thái</th>
                <th>Mã trên Moodle</th>
                <th>Định dạng</th>
                <th>Thời gian</th>
                <th>Ghi chú</th>
                <th>Chạy lại</th>
              </tr>
            </thead>
            <tbody>
              {publications.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.question_code || item.question_id}</strong>
                    <small>Phiên bản {item.question_version}</small>
                  </td>
                  <td>
                    <span>{item.target?.site_name || item.target?.moodle_site_id || '--'}</span>
                    <small>{MODE_LABEL[item.publication_mode || item.target?.mode] || 'Mô phỏng'} · {item.target?.course_id}/{item.target?.category_id}</small>
                  </td>
                  <td>
                    <span className={`publication-status publication-status--${publicationStatusClass(item.status)}`}>
                      {item.status_label || STATUS_LABEL[item.status] || item.status || 'Chưa rõ'}
                    </span>
                  </td>
                  <td>
                    <span>{item.moodle_question_ref_id || 'Chưa có'}</span>
                    {item.publication_mode === 'MOCK' && <small>Mã mô phỏng, không phải mã trên Moodle thật</small>}
                  </td>
                  <td>{(item.export_formats?.length ? item.export_formats.join(', ') : item.export_format || '').toUpperCase()}</td>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td className="publication-error">{item.error_message || item.message || (item.external_sync === false ? 'Chỉ ghi nhận trong hệ thống' : 'Không có')}</td>
                  <td>
                    {item.status === 'FAILED' ? (
                      <button
                        type="button"
                        className="publication-retry-button"
                        title="Chạy lại lượt đưa lên bị lỗi"
                        aria-label="Chạy lại lượt đưa lên bị lỗi"
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
          {publicationsLoading && <p className="moodle-empty">Đang tải...</p>}
          {!publicationsLoading && publications.length === 0 && <p className="moodle-empty">Không có lượt đưa lên nào phù hợp.</p>}
        </div>
      </section>

      {formOpen && (
        <div className="modal-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) closeForm(); }}>
          <form className="moodle-dialog" onSubmit={handleSave} role="dialog" aria-modal="true" aria-label={editingTarget ? 'Sửa kết nối Moodle' : 'Thêm kết nối Moodle'}>
            <div className="moodle-panel-heading">
              <div>
                <h2>{editingTarget ? `Sửa kết nối ${editingTarget.site_name}` : 'Thêm kết nối Moodle'}</h2>
                <p>Token truy cập Moodle không nhập ở đây; máy chủ đọc từ biến môi trường.</p>
              </div>
              <button type="button" className="moodle-close-button" onClick={closeForm} aria-label="Đóng">×</button>
            </div>
            <div className="form-grid">
              <label>
                Mã kết nối
                <input required value={form.site_key} disabled={Boolean(editingTarget)} onChange={(event) => updateForm('site_key', event.target.value)} placeholder="Ví dụ: moodle-ctu" />
              </label>
              <label>
                Tên hiển thị
                <input required value={form.site_name} onChange={(event) => updateForm('site_name', event.target.value)} />
              </label>
              <label>
                Chế độ
                <select value={form.mode} onChange={(event) => updateForm('mode', event.target.value)}>
                  <option value="MOCK">Mô phỏng (không gửi sang Moodle)</option>
                  <option value="REST_API">Moodle thật (REST API)</option>
                </select>
              </label>
              <label>
                Trạng thái
                <select value={form.is_active ? 'true' : 'false'} onChange={(event) => updateForm('is_active', event.target.value === 'true')}>
                  <option value="true">Đang dùng</option>
                  <option value="false">Đã khóa</option>
                </select>
              </label>
              <label className="form-span">
                Địa chỉ Moodle
                <input value={form.base_url || ''} onChange={(event) => updateForm('base_url', event.target.value)} placeholder="https://moodle.example.edu" />
              </label>
              <label className="form-span">
                Tên biến môi trường chứa token
                <input value={form.token_env_var || ''} onChange={(event) => updateForm('token_env_var', event.target.value)} placeholder="MOODLE_API_TOKEN" />
              </label>
              <label>
                Mã khoá học mặc định
                <input value={form.default_course_id} onChange={(event) => updateForm('default_course_id', event.target.value)} />
              </label>
              <label>
                Mã danh mục câu hỏi mặc định
                <input value={form.default_category_id} onChange={(event) => updateForm('default_category_id', event.target.value)} />
              </label>
              <div className="form-span role-toggle-group">
                <span>Ai được đưa câu hỏi lên qua kết nối này</span>
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
            {editingTarget?.last_check && (
              <p className={editingTarget.last_check.ok ? 'check-ok' : 'check-fail'}>
                <FontAwesomeIcon icon={editingTarget.last_check.ok ? faCheckCircle : faCircleExclamation} />
                Lần kiểm tra gần nhất: {editingTarget.last_check.message}
              </p>
            )}
            {formError && <p className="moodle-form-error" role="alert">{formError}</p>}
            <div className="form-actions">
              <button type="button" className="moodle-secondary-button" onClick={closeForm} disabled={saving}>Hủy</button>
              <button type="submit" className="moodle-primary-button" disabled={saving}>
                <FontAwesomeIcon icon={faFloppyDisk} />
                <span>{saving ? 'Đang lưu' : 'Lưu kết nối'}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default AdminMoodlePage;
