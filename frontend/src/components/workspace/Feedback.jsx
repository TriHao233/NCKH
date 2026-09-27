import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faCircleCheck,
  faCircleExclamation,
  faCircleInfo,
  faInbox,
  faRotateRight,
  faTriangleExclamation,
  faXmark,
} from '@fortawesome/free-solid-svg-icons';

const NOTICE_ICON = {
  info: faCircleInfo,
  success: faCircleCheck,
  warn: faTriangleExclamation,
  error: faCircleExclamation,
};

export function Notice({ tone = 'info', children, onDismiss }) {
  if (!children) return null;
  return (
    <div className={`ws-notice ws-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <FontAwesomeIcon icon={NOTICE_ICON[tone] || faCircleInfo} />
      <p>{children}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Đóng thông báo">
          <FontAwesomeIcon icon={faXmark} />
        </button>
      )}
    </div>
  );
}

/** Lỗi tải dữ liệu hiển thị ngay tại chỗ, kèm nút thử lại. */
export function ErrorState({ message, onRetry, compact = false }) {
  return (
    <div className={`ws-empty ws-empty--error ${compact ? 'ws-empty--compact' : ''}`} role="alert">
      <span className="ws-empty__icon"><FontAwesomeIcon icon={faCircleExclamation} /></span>
      <strong>Không tải được dữ liệu</strong>
      <p>{message || 'Kết nối tới máy chủ không thành công.'}</p>
      {onRetry && (
        <button type="button" className="btn btn--outline btn--sm" onClick={onRetry}>
          <FontAwesomeIcon icon={faRotateRight} />
          Thử lại
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon = faInbox, title, description, action, compact = false }) {
  return (
    <div className={`ws-empty ${compact ? 'ws-empty--compact' : ''}`}>
      <span className="ws-empty__icon"><FontAwesomeIcon icon={icon} /></span>
      {title && <strong>{title}</strong>}
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function SkeletonRows({ rows = 4, lines = 2 }) {
  return (
    <div className="ws-skeleton-rows" aria-busy="true" aria-label="Đang tải">
      {Array.from({ length: rows }, (_, row) => (
        <div className="ws-skeleton-row" key={row}>
          {Array.from({ length: lines }, (__, line) => (
            <span
              key={line}
              className="ws-skeleton"
              style={{ height: line === 0 ? 14 : 11, width: line === 0 ? `${62 - (row % 3) * 9}%` : `${88 - (row % 2) * 14}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
