import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronLeft, faChevronRight } from '@fortawesome/free-solid-svg-icons';

function Count({ value }) {
  if (value === undefined || value === null) return null;
  return <span className="ws-tab-count tabular">{value}</span>;
}

/** Tabs có bộ đếm (đổi chế độ xem trong cùng trang). */
export function Tabs({ items, value, onChange, label }) {
  return (
    <div className="ws-tabs" role="tablist" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          className={`ws-tab ${value === item.value ? 'ws-tab--active' : ''}`}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          <Count value={item.count} />
        </button>
      ))}
    </div>
  );
}

/** Nhóm nút chọn một (segmented control), có thể kèm bộ đếm. */
export function Segmented({ items, value, onChange, label }) {
  return (
    <div className="ws-segment" role="group" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          aria-pressed={value === item.value}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          <Count value={item.count} />
        </button>
      ))}
    </div>
  );
}

export function Pagination({ page, pageSize, total, loading = false, onChange }) {
  const pageCount = Math.max(1, Math.ceil((total || 0) / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total || 0);
  if (!total || total <= pageSize) return null;
  return (
    <div className="ws-pagination">
      <span className="tabular">{start}-{end} / {total}</span>
      <div>
        <button
          type="button"
          className="ws-icon-btn"
          aria-label="Trang trước"
          disabled={loading || page <= 1}
          onClick={() => onChange(Math.max(1, page - 1))}
        >
          <FontAwesomeIcon icon={faChevronLeft} />
        </button>
        <span className="ws-sr-only">Trang {page} / {pageCount}</span>
        <button
          type="button"
          className="ws-icon-btn"
          aria-label="Trang sau"
          disabled={loading || page >= pageCount}
          onClick={() => onChange(Math.min(pageCount, page + 1))}
        >
          <FontAwesomeIcon icon={faChevronRight} />
        </button>
      </div>
    </div>
  );
}
