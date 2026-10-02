import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getCatalogOverview } from '../api/catalog';
import ModelsTab from '../components/catalog/ModelsTab';
import PolicyTab from '../components/catalog/PolicyTab';
import PromptsTab from '../components/catalog/PromptsTab';
import SubjectsTab from '../components/catalog/SubjectsTab';
import '../css/CatalogAdminPage.css';

const CONFIG_TABS = [
  { id: 'subjects', label: 'Học phần' },
  { id: 'models', label: 'Mô hình AI' },
  { id: 'prompts', label: 'Mẫu prompt' },
  { id: 'policy', label: 'Tiêu chí đánh giá' },
];
const EMPTY_CATALOG = { subjects: [], ai_models: [], prompt_templates: [], evaluation_policies: [], runtime_config: {} };

function CatalogAdminPage() {
  const [catalog, setCatalog] = useState(EMPTY_CATALOG);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const tab = CONFIG_TABS.some((item) => item.id === requestedTab) ? requestedTab : 'subjects';

  // Tải lại sau khi lưu không thay cả trang bằng màn hình chờ, để giữ vị trí đang xem.
  const loadCatalog = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      setCatalog({ ...EMPTY_CATALOG, ...(await getCatalogOverview()) });
    } catch (err) {
      setError(err.message || 'Không tải được cấu hình');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    if (!toast || toast.type === 'error') return undefined;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const notify = useCallback((type, text) => setToast({ type, text }), []);
  const reload = useCallback(() => loadCatalog({ silent: true }), [loadCatalog]);

  // Chạy một thao tác lưu: báo kết quả, tải lại dữ liệu và trả về để biểu mẫu tự xử lý lỗi.
  const run = async (action, successText, { quiet = false } = {}) => {
    setSaving(true);
    try {
      const result = await action();
      await reload();
      if (successText) notify('success', successText);
      return { ok: true, result };
    } catch (err) {
      if (!quiet) notify('error', err.message || 'Lưu cấu hình thất bại');
      return { ok: false, error: err };
    } finally {
      setSaving(false);
    }
  };

  const runtimeConfig = catalog.runtime_config || {};
  const tabProps = { saving, run, notify, reload };

  return (
    <main className="catalog-page">
      <section className="catalog-header">
        <div>
          <span>Khu vực quản trị</span>
          <h1>Cấu hình hệ thống</h1>
        </div>
        <button type="button" className="catalog-ghost-button" onClick={() => loadCatalog()} disabled={loading || saving}>Làm mới</button>
      </section>
      <nav className="catalog-tabs" aria-label="Nhóm cấu hình">
        {CONFIG_TABS.map((item) => (
          <button
            type="button"
            key={item.id}
            className={tab === item.id ? 'is-active' : ''}
            aria-current={tab === item.id ? 'page' : undefined}
            onClick={() => setSearchParams(item.id === 'subjects' ? {} : { tab: item.id }, { replace: true })}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {error && <p className="catalog-error" role="alert">{error}</p>}
      {loading ? (
        <p className="catalog-empty">Đang tải cấu hình...</p>
      ) : (
        <section className="catalog-content">
          {tab === 'subjects' && <SubjectsTab subjects={catalog.subjects} {...tabProps} />}
          {tab === 'models' && <ModelsTab models={catalog.ai_models} runtimeConfig={runtimeConfig} {...tabProps} />}
          {tab === 'prompts' && (
            <PromptsTab templates={catalog.prompt_templates} promptSource={runtimeConfig.prompt_source} {...tabProps} />
          )}
          {tab === 'policy' && (
            <PolicyTab policies={catalog.evaluation_policies} fallbackPolicy={runtimeConfig.active_evaluation_policy} {...tabProps} />
          )}
        </section>
      )}
      {toast && (
        <div className={`catalog-toast catalog-toast--${toast.type}`} role={toast.type === 'error' ? 'alert' : 'status'}>
          <span>{toast.text}</span>
          <button type="button" className="catalog-toast-close" onClick={() => setToast(null)} aria-label="Đóng thông báo">×</button>
        </div>
      )}
    </main>
  );
}

export default CatalogAdminPage;
