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
  const [actionDialog, setActionDialog] = useState(null);
  const [dialogError, setDialogError] = useState('');

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
      setError(err.message || 'Không tải được kết nối Moodle');
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
      setError(err.message || 'Không tải được lịch sử xuất bản');
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
      setError(err.message || 'Lưu kết nối Moodle thất bại');
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
      setError(err.message || 'Kiểm tra kết nối thất bại');
    } finally {
      setCheckingKey('');
    }
  };

  const handleDeactivate = (target) => {
    setDialogError('');
    setActionDialog({ type: 'deactivate', target });
  };

  const handleRetryPublication = (item) => {
    setDialogError('');
    setActionDialog({ type: 'retry', item });
  };

  const confirmMoodleAction = async () => {
    if (!actionDialog) return;
    setDialogError('');
    setError('');
    if (actionDialog.type === 'deactivate') {
      setSaving(true);
      try {
        await deactivateMoodleTarget(actionDialog.target.site_key);
        setActionDialog(null);
        await loadTargets();
      } catch (err) {
        setDialogError(err.message || 'Khóa kết nối thất bại');
      } finally {
        setSaving(false);
      }
      return;
    }
    setRetryingId(actionDialog.item.id);
    try {
      await retryMoodlePublication(actionDialog.item.id);
      setActionDialog(null);
      await loadPublications();
    } catch (err) {
      setDialogError(err.message || 'Chạy lại xuất bản thất bại');
    } finally {
      setRetryingId('');
    }
  };

  const publicationPageCount = Math.max(
    1,
    Math.ceil(publicationTotal / PUBLICATION_PAGE_SIZE),
  );
  const dialogBusy = saving || Boolean(retryingId);
  const retryIsRealSync = (
    actionDialog?.type === 'retry'
    && actionDialog.item.publication_mode === 'REST_API'
    && actionDialog.item.external_sync !== false
  );

  return (
    <main className="admin-moodle-page">
      <section className="moodle-header">
        <div className="moodle-header__copy">
          <div className="moodle-eyebrow">
            <span aria-hidden="true"><FontAwesomeIcon icon={faPlug} /></span>
            Tích hợp
          </div>
          <h1>Moodle</h1>
          <p>Kết nối và theo dõi xuất bản.</p>
          <div className="moodle-mode-legend">
            <span><i className="mode-dot mode-dot--mock" /> Mô phỏng</span>
            <span><i className="mode-dot mode-dot--live" /> Kết nối thật</span>
          </div>
        </div>
        <div className="moodle-header__actions">
          <div className="moodle-connection-overview">
            <b>{targets.filter((target) => target.is_active).length}</b>
            <span>kết nối đang hoạt động</span>
          </div>
          <button type="button" className="moodle-primary-button" onClick={() => { loadTargets(); loadPublications(); }} disabled={loading || publicationsLoading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>Làm mới</span>
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
          <span>Tất cả</span>
        </button>
        <button
          type="button"
          className={publicationStatus === 'PUBLISHED' ? 'is-active' : ''}
          onClick={() => { setPublicationStatus('PUBLISHED'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--green"><FontAwesomeIcon icon={faCheckCircle} /></span>
          <b>{publicationSummary.published}</b>
          <span>Đã ghi</span>
        </button>
        <button
          type="button"
          className={`summary-danger ${publicationStatus === 'FAILED' ? 'is-active' : ''}`}
          onClick={() => { setPublicationStatus('FAILED'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--red"><FontAwesomeIcon icon={faCircleExclamation} /></span>
          <b>{publicationSummary.failed}</b>
          <span>Lỗi</span>
        </button>
        <button
          type="button"
          className={publicationStatus === 'PROCESSING' ? 'is-active' : ''}
          onClick={() => { setPublicationStatus('PROCESSING'); setPublicationPage(1); }}
        >
          <span className="moodle-summary-icon moodle-summary-icon--amber"><FontAwesomeIcon icon={faRotateRight} /></span>
          <b>{publicationSummary.pending}</b>
          <span>Đang xử lý</span>
        </button>
      </section>

      {error && <p className="moodle-error">{error}</p>}

      <section className="moodle-layout">
        <div className="moodle-target-panel">
          <div className="panel-heading">
            <div>
              <span>Kết nối</span>
              <h2>Cấu hình</h2>
              <small>{targets.length} kết nối</small>
            </div>
            <button type="button" onClick={newTarget}>+ Thêm</button>
          </div>

          {loading ? (
            <p className="moodle-empty">Đang tải kết nối...</p>
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
                      title="Khóa kết nối"
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
              {targets.length === 0 && <p className="moodle-empty">Chưa có kết nối.</p>}
            </div>
          )}
        </div>

        <form className="moodle-form-panel" onSubmit={handleSave}>
          <div className="panel-heading">
            <div>
              <span>{selectedTarget ? 'Đang sửa' : 'Kết nối mới'}</span>
              <h2>{selectedTarget ? selectedTarget.site_name : 'Thêm kết nối'}</h2>
              <small>
                {selectedTarget?.last_check?.ok
                  ? 'Đã kiểm tra kết nối'
                  : selectedTarget?.last_check?.message || 'Token lưu trong biến môi trường máy chủ'}
              </small>
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
              Kết nối thật. Kiểm tra chỉ đọc thông tin site; xuất bản sẽ gửi dữ liệu sang Moodle.
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
            <span>Gần đây</span>
            <h2>Lịch sử xuất bản</h2>
            <small>{publicationTotal} kết quả</small>
          </div>
          <div className="publication-filters">
            <select
              aria-label="Lọc theo điểm kết nối Moodle"
              value={siteFilter}
              onChange={(event) => { setSiteFilter(event.target.value); setPublicationPage(1); }}
            >
              <option value="all">Tất cả kết nối</option>
              {targets.map((target) => (
                <option key={target.site_key} value={target.site_key}>{target.site_name}</option>
              ))}
            </select>
            <select
              aria-label="Lọc theo trạng thái xuất bản"
              value={publicationStatus}
              onChange={(event) => { setPublicationStatus(event.target.value); setPublicationPage(1); }}
            >
              {Object.entries(STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <label>
              <FontAwesomeIcon icon={faSearch} />
              <input
                aria-label="Tìm trong nhật ký xuất bản Moodle"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Mã câu hỏi hoặc ghi chú"
              />
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
                    <small>Bản {item.question_version}</small>
                  </td>
                  <td>
                    <span>{item.target?.site_name || item.target?.moodle_site_id || 'Kết nối'}</span>
                    <small>{publicationModeLabel(item.publication_mode || item.target?.mode)} · {item.target?.course_id}/{item.target?.category_id}</small>
                  </td>
                  <td>
                    <span className={`publication-status publication-status--${publicationStatusClass(item.status)}`}>
                      {item.status_label || STATUS_LABEL[item.status] || item.status || 'Chưa rõ'}
                    </span>
                  </td>
                  <td>
                    <span>{item.moodle_question_ref_id || 'Chưa có'}</span>
                    {item.publication_mode === 'MOCK' && <small>Mã mô phỏng</small>}
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
          {publicationsLoading && <p className="moodle-empty">Đang tải lịch sử...</p>}
          {!publicationsLoading && publications.length === 0 && <p className="moodle-empty">Không có lượt xuất bản phù hợp.</p>}
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

      {actionDialog && (
        <div className="moodle-dialog-backdrop">
          <section
            className="moodle-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-action-dialog-title"
          >
            <header>
              <span>
                {actionDialog.type === 'deactivate'
                  ? actionDialog.target.site_key
                  : (actionDialog.item.question_code || actionDialog.item.question_id)}
              </span>
              <h2 id="moodle-action-dialog-title">
                {actionDialog.type === 'deactivate'
                  ? 'Khóa kết nối Moodle?'
                  : 'Chạy lại lượt xuất bản?'}
              </h2>
            </header>
            <div className="moodle-dialog__body">
              {actionDialog.type === 'deactivate' ? (
                <p>
                  <b>{actionDialog.target.site_name}</b> sẽ ngừng nhận dữ liệu mới. Lịch sử vẫn được giữ.
                </p>
              ) : (
                <>
                  <p>Đưa lượt xuất bản lỗi vào xử lý lại.</p>
                  <div className={retryIsRealSync ? 'danger' : 'safe'}>
                    {retryIsRealSync
                      ? 'Kết nối thật: dữ liệu có thể được gửi lại sang Moodle.'
                      : 'Mô phỏng: chỉ tạo lại bản ghi cục bộ.'}
                  </div>
                </>
              )}
              {dialogError && <p className="moodle-dialog__error" role="alert">{dialogError}</p>}
            </div>
            <footer>
              <button type="button" onClick={() => setActionDialog(null)} disabled={dialogBusy}>
                Hủy
              </button>
              <button
                type="button"
                className={actionDialog.type === 'deactivate' || retryIsRealSync ? 'danger' : 'primary'}
                onClick={confirmMoodleAction}
                disabled={dialogBusy}
              >
                {dialogBusy
                  ? 'Đang xử lý...'
                  : (actionDialog.type === 'deactivate' ? 'Khóa kết nối' : 'Chạy lại')}
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}

export default AdminMoodlePage;
