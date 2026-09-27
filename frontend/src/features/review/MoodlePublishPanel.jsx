import { useEffect, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faDownload, faUpload } from '@fortawesome/free-solid-svg-icons';
import { listMoodleTargets } from '../../api/adminMoodle';
import { exportQuestionMoodle, publishQuestionToMoodle } from '../../api/questions';
import { Notice } from '../../components/workspace/Feedback';
import { PUBLICATION_STATUS_LABEL, formatDateTime, refId } from './reviewModel';

function downloadText(filename, content, mimeType) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function publicationError(item) {
  if (!item?.error) return item?.error_message || '';
  return typeof item.error === 'string' ? item.error : (item.error.message || '');
}

/**
 * Xuất bản câu đã duyệt lên Moodle. Quản trị viên chọn được điểm đồng bộ;
 * người duyệt dùng điểm đồng bộ mặc định (backend kiểm tra allowed_roles).
 */
function MoodlePublishPanel({ question, user, publications, onPublished }) {
  const isAdminUser = user?.role === 'Admin';
  const [targets, setTargets] = useState([]);
  const [targetId, setTargetId] = useState('');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!isAdminUser) return;
    listMoodleTargets({ includeInactive: false })
      .then((result) => {
        const usable = (result.items || []).filter((target) => target.is_active !== false
          && (target.allowed_roles?.length ? target.allowed_roles.includes(user.role) : true));
        setTargets(usable);
        setTargetId((current) => current || usable[0]?.site_key || '');
      })
      .catch(() => setTargets([]));
  }, [isAdminUser, user?.role]);

  const published = question.publication_status === 'PUBLISHED';

  const publish = async () => {
    setBusy('publish');
    setMessage(null);
    try {
      await publishQuestionToMoodle(question.id, {
        expected_version: question.current_version,
        export_format: 'BOTH',
        mock: true,
        ...(targetId ? { target_id: targetId } : {}),
      });
      setMessage({ tone: 'success', text: 'Đã đồng bộ câu hỏi lên Moodle (chế độ mô phỏng).' });
      await onPublished?.();
    } catch (error) {
      setMessage({ tone: 'error', text: error.message || 'Đồng bộ thất bại.' });
    } finally {
      setBusy('');
    }
  };

  const exportFile = async (format) => {
    setBusy(format);
    setMessage(null);
    try {
      const content = await exportQuestionMoodle(question.id, format);
      downloadText(
        `${question.question_code || 'cau-hoi'}.${format === 'xml' ? 'xml' : 'gift'}`,
        typeof content === 'string' ? content : JSON.stringify(content),
        format === 'xml' ? 'application/xml' : 'text/plain',
      );
    } catch (error) {
      setMessage({ tone: 'error', text: error.message || 'Không tải được tệp.' });
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="rv-publish">
      <div className="rv-section-head">
        <span className="ws-label">Xuất bản Moodle</span>
        <span className={`ws-pill ${published ? 'ws-pill--success' : 'ws-pill--outline'}`}>
          {PUBLICATION_STATUS_LABEL[question.publication_status] || 'Chưa đồng bộ'}
        </span>
      </div>
      {isAdminUser && targets.length > 0 && (
        <label className="ws-field">
          <span>Điểm đồng bộ</span>
          <select className="ws-select" value={targetId} onChange={(event) => setTargetId(event.target.value)}>
            {targets.map((target) => <option key={target.site_key} value={target.site_key}>{target.site_name}</option>)}
          </select>
        </label>
      )}
      <button
        type="button"
        className="btn btn--primary"
        disabled={Boolean(busy) || published}
        title={published ? 'Câu hỏi đã có trên Moodle' : undefined}
        onClick={publish}
      >
        <FontAwesomeIcon icon={faUpload} />
        {busy === 'publish' ? 'Đang đồng bộ...' : (published ? 'Đã đồng bộ' : 'Xuất bản')}
      </button>
      <div className="rv-decide__row">
        <button type="button" className="btn btn--outline btn--sm" disabled={Boolean(busy)} onClick={() => exportFile('gift')}>
          <FontAwesomeIcon icon={faDownload} />
          Tệp GIFT
        </button>
        <button type="button" className="btn btn--outline btn--sm" disabled={Boolean(busy)} onClick={() => exportFile('xml')}>
          <FontAwesomeIcon icon={faDownload} />
          Tệp XML
        </button>
      </div>
      {message && <Notice tone={message.tone} onDismiss={() => setMessage(null)}>{message.text}</Notice>}
      {publications.length > 0 && (
        <ul className="rv-sync-list">
          {publications.slice(0, 5).map((item) => (
            <li key={refId(item)}>
              <span className={`ws-pill ${item.status === 'FAILED' ? 'ws-pill--danger' : 'ws-pill--success'}`}>
                {item.status === 'FAILED' ? 'Đồng bộ lỗi' : 'Đã đồng bộ'}
              </span>
              <span className="ws-hint">{formatDateTime(item.published_at || item.created_at)}</span>
              {publicationError(item) && <small className="ws-field-error">{publicationError(item)}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default MoodlePublishPanel;
