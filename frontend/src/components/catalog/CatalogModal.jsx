import React, { useEffect } from 'react';

function CatalogModal({ title, onClose, wide = false, children }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div className={`catalog-modal ${wide ? 'catalog-modal--wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="catalog-modal-head">
          <h2>{title}</h2>
          <button type="button" className="catalog-ghost-button" onClick={onClose} aria-label="Đóng">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default CatalogModal;
