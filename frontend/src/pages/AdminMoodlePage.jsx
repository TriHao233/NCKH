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

const PUBLICATION_PAGE_SIZE = 50;

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

function publicationModeLabel(mode) {
  return mode === 'REST_API' ? 'Đồng bộ Moodle thật' : 'Mô phỏng cục bộ';
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
  const [publicationPage, setPublicationPage] = useState(1);
  const [form, setForm] = useState(emptyForm);
  const [selectedKey, setSelectedKey] = useState('');
  const [isCreatingTarget, setIsCreatingTarget] = useState(false);
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
    const handle = setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPublicationPage(1);
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const loadTargets = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listMoodleTargets();
      const items = result.items || [];
      setTargets(items);
      if (!selectedKey && !isCreatingTarget && items[0]) {
        setSelectedKey(items[0].site_key);
        setForm(formFromTarget(items[0]));
      }
    } catch (err) {
      setError(err.message || 'Không tải được Moodle target');
    } finally {
      setLoading(false);
    }
  }, [isCreatingTarget, selectedKey]);

  const loadPublications = useCallback(async () => {
    setPublicationsLoading(true);
    try {
      const result = await listMoodlePublications({
        page: publicationPage,
        pageSize: PUBLICATION_PAGE_SIZE,
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
  }, [publicationPage, publicationStatus, searchTerm, siteFilter]);

  useEffect(() => {
    loadTargets();
  }, [loadTargets]);

  useEffect(() => {
    loadPublications();
  }, [loadPublications]);

  const selectedTarget = useMemo(
    () => (isCreatingTarget ? null : targets.find((target) => target.site_key === selectedKey) || null),
    [isCreatingTarget, selectedKey, targets],
  );

  const pickTarget = (target) => {
    setIsCreatingTarget(false);
    setSelectedKey(target.site_key);
    setForm(formFromTarget(target));
  };

  const newTarget = () => {
    setIsCreatingTarget(true);
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
      setIsCreatingTarget(false);
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
    const realSync = item.publication_mode === 'REST_API' && item.external_sync !== false;
    const consequence = realSync
      ? 'Thao tác này có thể gửi lại câu hỏi sang Moodle thật.'
      : 'Thao tác này chỉ tạo lại bản ghi mô phỏng cục bộ.';
    if (!window.confirm(`Chạy lại lượt xuất bản "${item.question_code || item.question_id}"? ${consequence}`)) return;
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

  const publicationPageCount = Math.max(
    1,
    Math.ceil(publicationTotal / PUBLICATION_PAGE_SIZE),
  );

  return (
    <main className="admin-moodle-page">
      <section className="moodle-header">
        <div className="moodle-header__copy">
          <div className="moodle-eyebrow">
            <span aria-hidden="true"><FontAwesomeIcon icon={faPlug} /></span>
            Tích hợp giảng dạy
          </div>
          <h1>Trung tâm kết nối Moodle</h1>
          <p>Thiết lập nơi nhận câu hỏi, kiểm tra kết nối và theo dõi từng lượt đồng bộ từ một màn hình duy nhất.</p>
          <div className="moodle-mode-legend">
            <span><i className="mode-dot mode-dot--mock" /> Mô phỏng an toàn</span>
            <span><i className="mode-dot mode-dot--live" /> Đồng bộ Moodle thật</span>
          </div>
        </div>
        <div className="moodle-header__actions">
          <div className="moodle-connection-overview">
            <b>{targets.filter((target) => target.is_active).length}</b>
            <span>điểm kết nối đang hoạt động</span>
          </div>
          <button type="button" className="moodle-primary-button" onClick={() => { loadTargets(); loadPublications(); }} disabled={loading || publicationsLoading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>Làm mới dữ liệu</span>
          </button>
        </div>
      </section>

      <section className="moodle-summary">
        <button
          type="button"
          className={publicationStatus === 'all' ? 'is-active' : ''}
          onClick={() => { setPublicationStatus('all'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--blue"><FontAwesomeIcon icon={faPlug} /></span>
          <b>{publicationSummary.total}</b>
          <span>Tổng lượt xuất bản</span>
          <small>Toàn bộ hoạt động</small>
        </button>
        <button
          type="button"
          className={publicationStatus === 'PUBLISHED' ? 'is-active' : ''}
          onClick={() => { setPublicationStatus('PUBLISHED'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--green"><FontAwesomeIcon icon={faCheckCircle} /></span>
          <b>{publicationSummary.published}</b>
          <span>Đã ghi nhận</span>
          <small>{publicationSummary.simulated || 0} lượt mô phỏng</small>
        </button>
        <button
          type="button"
          className={`summary-danger ${publicationStatus === 'FAILED' ? 'is-active' : ''}`}
          onClick={() => { setPublicationStatus('FAILED'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--red"><FontAwesomeIcon icon={faCircleExclamation} /></span>
          <b>{publicationSummary.failed}</b>
          <span>Xuất bản lỗi</span>
          <small>Cần kiểm tra lại</small>
        </button>
        <button
          type="button"
          className={publicationStatus === 'PROCESSING' ? 'is-active' : ''}
          onClick={() => { setPublicationStatus('PROCESSING'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--amber"><FontAwesomeIcon icon={faRotateRight} /></span>
          <b>{publicationSummary.pending}</b>
          <span>Đang xử lý</span>
          <small>Đang chờ hoặc đồng bộ</small>
        </button>
      </section>

      {error && <p className="moodle-error">{error}</p>}

      <section className="moodle-layout">
        <div className="moodle-target-panel">
          <div className="panel-heading">
            <div>
              <span>Điểm đến</span>
              <h2>Cấu hình kết nối</h2>
              <small>{targets.length} cấu hình Moodle</small>
            </div>
            <button type="button" onClick={newTarget}>+ Thêm kết nối</button>
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
                    <span className="target-brand" aria-hidden="true">M</span>
                    <div className="target-title">
                      <strong>{target.site_name}</strong>
                      <small>{target.site_key}</small>
                    </div>
                    <span className={`target-check ${target.last_check?.ok ? 'target-check--ok' : ''}`}>
                      {checkText(target)}
                    </span>
                  </div>
                  <div className="target-meta">
                    <span className={`target-mode target-mode--${target.mode === 'REST_API' ? 'live' : 'mock'}`}>
                      {target.mode === 'REST_API' ? 'Moodle thật' : 'Mô phỏng'}
                    </span>
                    <span>Khóa học {target.default_course_id || '—'}</span>
                    <span>Danh mục {target.default_category_id || '—'}</span>
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
                      <span>{checkingKey === target.site_key ? 'Đang kiểm tra' : 'Kiểm tra'}</span>
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
                      <span>Khóa</span>
                    </button>
                    <small>Kiểm tra gần nhất: {formatDateTime(target.last_check?.checked_at)}</small>
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
              <span>{selectedTarget ? 'Đang chỉnh sửa' : 'Cấu hình mới'}</span>
              <h2>{selectedTarget ? selectedTarget.site_name : 'Thêm điểm kết nối'}</h2>
              <small>{selectedTarget?.last_check?.message || 'Token được bảo vệ trong biến môi trường trên máy chủ'}</small>
            </div>
            <span className={`moodle-form-mode moodle-form-mode--${form.mode === 'REST_API' ? 'live' : 'mock'}`}>
              {form.mode === 'REST_API' ? 'Đồng bộ thật' : 'Mô phỏng'}
            </span>
          </div>
          <div className="form-grid">
            <label>
              <span>Mã cấu hình</span>
              <input value={form.site_key} onChange={(event) => updateForm('site_key', event.target.value)} placeholder="ctu-main" />
            </label>
            <label>
              <span>Tên hiển thị</span>
              <input value={form.site_name} onChange={(event) => updateForm('site_name', event.target.value)} placeholder="Moodle Đại học Cần Thơ" />
            </label>
            <label>
              <span>Kiểu kết nối</span>
              <select value={form.mode} onChange={(event) => updateForm('mode', event.target.value)}>
                <option value="MOCK">Mô phỏng — chỉ lưu cục bộ</option>
                <option value="REST_API">REST API — kết nối Moodle thật</option>
              </select>
            </label>
            <label>
              <span>Trạng thái sử dụng</span>
              <select value={form.is_active ? 'true' : 'false'} onChange={(event) => updateForm('is_active', event.target.value === 'true')}>
                <option value="true">Hoạt động</option>
                <option value="false">Đã khóa</option>
              </select>
            </label>
            <label className="form-span">
              <span>Địa chỉ Moodle</span>
              <input value={form.base_url || ''} onChange={(event) => updateForm('base_url', event.target.value)} placeholder="https://moodle.example.edu" />
            </label>
            <label>
              <span>Biến môi trường chứa token</span>
              <input value={form.token_env_var || ''} onChange={(event) => updateForm('token_env_var', event.target.value)} placeholder="MOODLE_API_TOKEN" />
            </label>
            <label>
              <span>Khóa học mặc định</span>
              <input value={form.default_course_id} onChange={(event) => updateForm('default_course_id', event.target.value)} />
            </label>
            <label>
              <span>Danh mục câu hỏi</span>
              <input value={form.default_category_id} onChange={(event) => updateForm('default_category_id', event.target.value)} />
            </label>
            <div className="form-span role-toggle-group">
              <span>Vai trò được phép xuất bản</span>
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
          {form.mode === 'REST_API' && (
            <p className="moodle-real-sync-warning">
              Đây là cấu hình Moodle thật. Nút kiểm tra chỉ đọc thông tin site; thao tác xuất bản ở màn kiểm duyệt mới gửi câu hỏi ra ngoài hệ thống.
            </p>
          )}
          <div className="form-actions">
            {selectedTarget?.last_check && (
              <span className={selectedTarget.last_check.ok ? 'check-ok' : 'check-fail'}>
                <FontAwesomeIcon icon={selectedTarget.last_check.ok ? faCheckCircle : faCircleExclamation} />
                {selectedTarget.last_check.message}
              </span>
            )}
            <button type="submit" disabled={saving}>
              <FontAwesomeIcon icon={faFloppyDisk} />
              <span>{saving ? 'Đang lưu' : 'Lưu cấu hình'}</span>
            </button>
          </div>
        </form>
      </section>

      <section className="publication-panel">
        <div className="panel-heading">
          <div>
            <span>Hoạt động gần đây</span>
            <h2>Nhật ký xuất bản</h2>
            <small>{publicationTotal} kết quả theo bộ lọc hiện tại</small>
          </div>
          <div className="publication-filters">
            <select value={siteFilter} onChange={(event) => { setSiteFilter(event.target.value); setPublicationPage(1); }}>
              <option value="all">Tất cả site</option>
              {targets.map((target) => (
                <option key={target.site_key} value={target.site_key}>{target.site_name}</option>
              ))}
            </select>
            <select value={publicationStatus} onChange={(event) => { setPublicationStatus(event.target.value); setPublicationPage(1); }}>
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
                <th>Câu hỏi</th>
                <th>Điểm kết nối</th>
                <th>Trạng thái</th>
                <th>Mã Moodle</th>
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
                    <span>{item.target?.site_name || item.target?.moodle_site_id || 'Điểm kết nối'}</span>
                    <small>{publicationModeLabel(item.publication_mode || item.target?.mode)} · {item.target?.course_id}/{item.target?.category_id}</small>
                  </td>
                  <td>
                    <span className={`publication-status publication-status--${publicationStatusClass(item.status)}`}>
                      {item.status_label || STATUS_LABEL[item.status] || item.status || 'Chưa rõ'}
                    </span>
                  </td>
                  <td>
                    <span>{item.moodle_question_ref_id || 'Chưa có'}</span>
                    {item.publication_mode === 'MOCK' && <small>Mã mô phỏng, không phải ID từ Moodle</small>}
                  </td>
                  <td>{item.export_formats?.length ? item.export_formats.join(', ') : item.export_format}</td>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td className="publication-error">{item.error_message || item.message || (item.external_sync === false ? 'Ghi nhận cục bộ' : 'Không có')}</td>
                  <td>
                    {item.status === 'FAILED' ? (
                      <button
                        type="button"
                        className="publication-retry-button"
                        title="Chạy lại lượt xuất bản lỗi"
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
        {!publicationsLoading && publicationTotal > 0 && (
          <div className="moodle-pagination">
            <button
              type="button"
              disabled={publicationPage <= 1}
              onClick={() => setPublicationPage((current) => Math.max(1, current - 1))}
            >
              Trang trước
            </button>
            <span>Trang {publicationPage}/{publicationPageCount} · {publicationTotal} kết quả</span>
            <button
              type="button"
              disabled={publicationPage >= publicationPageCount}
              onClick={() => setPublicationPage((current) => Math.min(publicationPageCount, current + 1))}
            >
              Trang sau
            </button>
          </div>
        )}
      </section>
    </main>
  );
}

export default AdminMoodlePage;
