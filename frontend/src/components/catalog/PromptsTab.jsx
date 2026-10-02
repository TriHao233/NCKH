import React, { useEffect, useMemo, useState } from 'react';
import { activatePromptTemplate, savePromptTemplate, testPromptTemplate } from '../../api/catalog';
import { diffLines, diffSummary } from '../../utils/lineDiff';
import { groupPrompts, promptKindLabel } from '../../utils/promptCatalog';
import CatalogModal from './CatalogModal';

const EMPTY_NEW_PROMPT = { template_key: '', kind: '', name: '', prompt_body: '' };

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('vi-VN');
}

function PromptsTab({ templates, promptSource, saving, run, notify }) {
  const [search, setSearch] = useState('');
  const [selectedKey, setSelectedKey] = useState('');
  const [viewedVersion, setViewedVersion] = useState(null);
  const [draft, setDraft] = useState({ key: '', name: '', body: '' });
  const [showDiff, setShowDiff] = useState(false);
  const [preview, setPreview] = useState(null);
  const [testing, setTesting] = useState(false);
  const [newPrompt, setNewPrompt] = useState(null);
  const [newPromptError, setNewPromptError] = useState('');

  const usesDatabase = promptSource === 'db';
  const allItems = useMemo(() => groupPrompts(templates).flatMap((group) => group.items), [templates]);
  const groups = useMemo(() => groupPrompts(templates, search), [templates, search]);
  const kinds = useMemo(() => [...new Set(templates.map((template) => template.kind))], [templates]);
  const current = allItems.find((item) => item.key === selectedKey) || allItems[0] || null;
  const viewed = current
    ? current.versions.find((version) => version.version === viewedVersion) || current.active || current.latest
    : null;
  const dirty = Boolean(viewed) && draft.key === current.key
    && (draft.body !== viewed.prompt_body || draft.name !== (viewed.name || ''));

  const openVersion = (record) => {
    setSelectedKey(record.template_key);
    setViewedVersion(record.version);
    setDraft({ key: record.template_key, name: record.name || '', body: record.prompt_body || '' });
    setShowDiff(false);
    setPreview(null);
  };

  // Nạp nội dung vào ô soạn khi mở tab hoặc khi mục đang chọn chưa có bản soạn.
  useEffect(() => {
    if (viewed && draft.key !== current.key) openVersion(viewed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.key, viewed?.version]);

  const confirmDiscard = () => !dirty || window.confirm('Nội dung đang soạn chưa lưu sẽ mất. Vẫn chuyển?');

  const selectItem = (item) => {
    if (item.key === current?.key || !confirmDiscard()) return;
    openVersion(item.active || item.latest);
  };

  const selectVersion = (version) => {
    if (version.version === viewed.version || !confirmDiscard()) return;
    openVersion(version);
  };

  const handleSave = async (activate) => {
    if (!draft.body.trim()) {
      notify('error', 'Nội dung prompt không được để trống.');
      return;
    }
    if (activate) {
      const effect = usesDatabase
        ? 'Phiên bản mới sẽ được dùng ngay cho các lượt chạy tiếp theo.'
        : 'Phiên bản mới sẽ thành bản đang dùng trong cơ sở dữ liệu (máy chủ hiện vẫn đọc từ file).';
      if (!window.confirm(`Lưu thành phiên bản mới và dùng ngay? ${effect}`)) return;
    }
    const outcome = await run(
      () => savePromptTemplate({
        template_key: current.key,
        kind: current.kind,
        name: draft.name.trim() || current.latest.name || current.key,
        prompt_body: draft.body,
        create_new_version: true,
        is_active: activate,
      }),
      activate ? 'Đã lưu và dùng phiên bản mới.' : 'Đã lưu bản nháp (chưa dùng).',
    );
    if (outcome.ok) openVersion(outcome.result);
  };

  const handleActivate = async (isActive) => {
    if (!isActive && !window.confirm('Ngừng dùng phiên bản này? Khi không có bản nào đang dùng, hệ thống lấy nội dung trong file .txt cho mục này.')) return;
    await run(
      () => activatePromptTemplate({ template_key: current.key, version: viewed.version, is_active: isActive }),
      isActive ? `Đã chuyển sang dùng phiên bản ${viewed.version}.` : `Đã ngừng dùng phiên bản ${viewed.version}.`,
    );
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      // Đang soạn dở thì thử đúng nội dung trong ô, ngược lại thử phiên bản đang xem.
      setPreview(await testPromptTemplate(
        dirty
          ? { template_key: current.key, prompt_body: draft.body }
          : { template_key: current.key, version: viewed.version },
      ));
    } catch (err) {
      notify('error', err.message || 'Không chạy thử được prompt');
    } finally {
      setTesting(false);
    }
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    const key = newPrompt.template_key.trim();
    if (allItems.some((item) => item.key === key)) {
      setNewPromptError('Mã prompt này đã có. Hãy chọn nó trong danh sách để tạo phiên bản mới.');
      return;
    }
    const outcome = await run(
      () => savePromptTemplate({
        template_key: key,
        kind: newPrompt.kind.trim().toUpperCase(),
        name: newPrompt.name.trim(),
        prompt_body: newPrompt.prompt_body,
        create_new_version: true,
        is_active: false,
      }),
      'Đã tạo prompt mới ở dạng bản nháp.',
      { quiet: true },
    );
    if (outcome.ok) {
      setNewPrompt(null);
      openVersion(outcome.result);
    } else {
      setNewPromptError(outcome.error?.message || 'Tạo prompt thất bại');
    }
  };

  const diffRows = showDiff && current?.active ? diffLines(current.active.prompt_body || '', draft.body) : [];
  const diffCount = diffSummary(diffRows);
  const canCompare = Boolean(current?.active) && (dirty || viewed?.version !== current.active.version);
  const previewWarnings = (preview?.warnings || []).filter((warning) => !warning.includes('PROMPT_SOURCE'));

  return (
    <div className="catalog-card">
      <div className="catalog-card-title-row">
        <div>
          <h2>Mẫu prompt</h2>
          <p className="catalog-card-note">Các đoạn hướng dẫn được ghép lại để AI sinh và thẩm định câu hỏi. Mỗi lần lưu tạo một phiên bản mới, bản cũ được giữ nguyên.</p>
        </div>
        <button type="button" onClick={() => { setNewPromptError(''); setNewPrompt(EMPTY_NEW_PROMPT); }} disabled={saving}>Thêm prompt</button>
      </div>

      {!usesDatabase && (
        <p className="catalog-banner">
          Máy chủ đang đọc prompt từ các file .txt, nên nội dung ở đây chưa có hiệu lực.
          Bạn vẫn soạn, lưu và chạy thử được; các bản này sẽ được dùng khi máy chủ chuyển sang đọc từ cơ sở dữ liệu.
        </p>
      )}

      <div className="prompt-layout">
        <div className="prompt-side">
          <input
            type="search"
            className="catalog-input"
            aria-label="Tìm prompt"
            placeholder="Tìm theo tên hoặc mã"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className="prompt-groups">
            {groups.map((group) => (
              <section key={group.kind}>
                <h4>{group.label} ({group.items.length})</h4>
                {group.items.map((item) => (
                  <button
                    type="button"
                    key={item.key}
                    className={`prompt-item ${current?.key === item.key ? 'active' : ''}`}
                    onClick={() => selectItem(item)}
                  >
                    <b>{item.title}</b>
                    <small>
                      {item.active ? `Đang dùng phiên bản ${item.active.version}` : 'Chưa có bản đang dùng'}
                      {item.versions.length > 1 && ` · ${item.versions.length} phiên bản`}
                    </small>
                  </button>
                ))}
              </section>
            ))}
            {groups.length === 0 && <p className="catalog-empty-note">{templates.length ? 'Không có prompt phù hợp.' : 'Chưa có prompt nào trong cơ sở dữ liệu.'}</p>}
          </div>
        </div>

        {current && viewed ? (
          <div className="prompt-detail">
            <div className="catalog-detail-head">
              <div>
                <h3>{current.title}</h3>
                <p>{promptKindLabel(current.kind)} · mã {current.key}</p>
              </div>
            </div>

            <div className="prompt-versions" role="group" aria-label="Phiên bản">
              {current.versions.map((version) => (
                <button
                  type="button"
                  key={version.version}
                  className={`catalog-ghost-button ${viewed.version === version.version ? 'is-active' : ''}`}
                  title={formatDateTime(version.created_at)}
                  onClick={() => selectVersion(version)}
                >
                  Phiên bản {version.version}{version.is_active ? ' · đang dùng' : ''}
                </button>
              ))}
            </div>

            <label className="catalog-field">
              <span>Tên prompt</span>
              <input className="catalog-input" maxLength={160} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label className="catalog-field">
              <span>
                Nội dung · {draft.body.length} ký tự
                {dirty && <em className="catalog-badge catalog-badge--default">Chưa lưu</em>}
              </span>
              <textarea
                className="prompt-editor"
                spellCheck={false}
                value={draft.body}
                onChange={(event) => setDraft({ ...draft, body: event.target.value })}
              />
            </label>

            <div className="prompt-actions">
              <button type="button" className="catalog-ghost-button" onClick={handleTest} disabled={testing || !draft.body.trim()}>
                {testing ? 'Đang chạy thử...' : 'Chạy thử'}
              </button>
              {canCompare && (
                <button type="button" className="catalog-ghost-button" onClick={() => setShowDiff((value) => !value)}>
                  {showDiff ? 'Ẩn so sánh' : 'So với bản đang dùng'}
                </button>
              )}
              <span className="prompt-actions-spacer" />
              {dirty ? (
                <>
                  <button type="button" className="catalog-ghost-button" onClick={() => openVersion(viewed)} disabled={saving}>Bỏ thay đổi</button>
                  <button type="button" className="catalog-ghost-button" onClick={() => handleSave(false)} disabled={saving}>Lưu bản nháp</button>
                  <button type="button" onClick={() => handleSave(true)} disabled={saving}>Lưu và dùng ngay</button>
                </>
              ) : viewed.is_active ? (
                <button type="button" className="catalog-ghost-button" onClick={() => handleActivate(false)} disabled={saving}>Ngừng dùng</button>
              ) : (
                <button type="button" onClick={() => handleActivate(true)} disabled={saving}>Dùng phiên bản này</button>
              )}
            </div>

            {showDiff && current.active && (
              <div className="prompt-preview">
                <b>So với phiên bản {current.active.version} đang dùng · thêm {diffCount.added} dòng, bớt {diffCount.removed} dòng</b>
                <pre className="prompt-diff">
                  {diffRows.map((row, index) => (
                    <span className={`prompt-diff-${row.type}`} key={index}>
                      {row.type === 'added' ? '+ ' : row.type === 'removed' ? '- ' : '  '}{row.text}{'\n'}
                    </span>
                  ))}
                </pre>
              </div>
            )}

            {preview && (
              <div className="prompt-preview">
                <b>
                  {preview.preview_mode === 'assembled'
                    ? `Prompt hoàn chỉnh sau khi ghép · ${preview.length} ký tự`
                    : `Nội dung đoạn prompt · ${preview.length} ký tự`}
                </b>
                {previewWarnings.map((warning) => <p className="catalog-card-note" key={warning}>{warning}</p>)}
                <pre>{preview.rendered_prompt}</pre>
              </div>
            )}
          </div>
        ) : (
          <p className="catalog-empty-note">Chọn một prompt ở danh sách bên trái.</p>
        )}
      </div>

      {newPrompt && (
        <CatalogModal title="Thêm prompt" onClose={() => setNewPrompt(null)} wide>
          <form className="catalog-form" onSubmit={handleCreate}>
            <div className="catalog-columns">
              <label className="catalog-field">
                <span>Mã prompt</span>
                <input required maxLength={120} placeholder="Ví dụ: question_type:tu_luan" value={newPrompt.template_key} onChange={(event) => setNewPrompt({ ...newPrompt, template_key: event.target.value })} />
              </label>
              <label className="catalog-field">
                <span>Nhóm</span>
                <input required maxLength={80} list="prompt-kinds" placeholder="Chọn hoặc nhập nhóm" value={newPrompt.kind} onChange={(event) => setNewPrompt({ ...newPrompt, kind: event.target.value })} />
                <datalist id="prompt-kinds">
                  {kinds.map((kind) => <option key={kind} value={kind}>{promptKindLabel(kind)}</option>)}
                </datalist>
              </label>
            </div>
            <label className="catalog-field">
              <span>Tên prompt</span>
              <input required maxLength={160} value={newPrompt.name} onChange={(event) => setNewPrompt({ ...newPrompt, name: event.target.value })} />
            </label>
            <label className="catalog-field">
              <span>Nội dung</span>
              <textarea required rows={12} spellCheck={false} value={newPrompt.prompt_body} onChange={(event) => setNewPrompt({ ...newPrompt, prompt_body: event.target.value })} />
            </label>
            {newPromptError && <p className="catalog-form-error" role="alert">{newPromptError}</p>}
            <div className="catalog-form-actions">
              <button type="button" className="catalog-ghost-button" onClick={() => setNewPrompt(null)} disabled={saving}>Hủy</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu bản nháp'}</button>
            </div>
          </form>
        </CatalogModal>
      )}
    </div>
  );
}

export default PromptsTab;
