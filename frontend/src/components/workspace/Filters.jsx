import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faFilter, faXmark } from '@fortawesome/free-solid-svg-icons';

/** Nút mở khung "Bộ lọc" kèm số bộ lọc đang bật (giống trang Giảng viên). */
export function FilterToggle({ open, count, onToggle }) {
  return (
    <button
      type="button"
      className={`btn btn--outline ws-filter-toggle ${open ? 'is-open' : ''}`}
      aria-expanded={open}
      onClick={onToggle}
    >
      <FontAwesomeIcon icon={faFilter} />
      Bộ lọc
      {count > 0 && <span className="ws-filter-toggle__badge">{count}</span>}
    </button>
  );
}

/**
 * Chip cho các bộ lọc đang bật; bấm x để gỡ.
 * chips: [{ key, label, onRemove }]
 */
export function FilterChips({ chips, onClearAll }) {
  if (!chips.length) return null;
  return (
    <div className="ws-chips" aria-label="Bộ lọc đang áp dụng">
      {chips.map((chip) => (
        <span className="ws-chip" key={chip.key}>
          {chip.label}
          <button type="button" onClick={chip.onRemove} aria-label={`Bỏ lọc ${chip.label}`}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </span>
      ))}
      {chips.length > 1 && onClearAll && (
        <button type="button" className="ws-link-btn" onClick={onClearAll}>Xoá tất cả</button>
      )}
    </div>
  );
}
