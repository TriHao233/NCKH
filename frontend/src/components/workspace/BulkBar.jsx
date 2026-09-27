/** Thanh hành động hàng loạt nổi ở đáy màn hình khi có dòng được chọn. */
function BulkBar({ count, onClear, children }) {
  if (!count) return null;
  return (
    <div className="ws-bulkbar" role="region" aria-label="Thao tác với các dòng đã chọn">
      <span className="ws-bulkbar__count tabular">{count} đã chọn</span>
      <div className="ws-bulkbar__actions">{children}</div>
      <button type="button" className="ws-link-btn" onClick={onClear}>Bỏ chọn</button>
    </div>
  );
}

export default BulkBar;
