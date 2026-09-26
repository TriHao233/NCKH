import { useEffect, useRef } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faXmark } from '@fortawesome/free-solid-svg-icons';

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Ngăn kéo trượt từ phải (~480px) để xem chi tiết hoặc sửa nhanh mà không rời trang.
 * Đóng bằng Esc hoặc bấm nền (khi không bận). Có thể dùng như một form (as="form").
 */
function Drawer({
  open,
  title,
  subtitle,
  onClose,
  busy = false,
  wide = false,
  footer,
  children,
  as: Container = 'div',
  onSubmit,
}) {
  const panelRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const busyRef = useRef(busy);
  busyRef.current = busy;

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const timer = window.setTimeout(() => {
      const target = panelRef.current?.querySelector('[data-autofocus]')
        || panelRef.current?.querySelector(`.ws-drawer__body ${FOCUSABLE}`)
        || panelRef.current?.querySelector(FOCUSABLE);
      target?.focus();
    }, 40);
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busyRef.current) {
        event.stopPropagation();
        onCloseRef.current?.();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && document.contains(previousFocus)) previousFocus.focus();
    };
  }, [open]);

  if (!open) return null;

  const containerProps = Container === 'form'
    ? {
        noValidate: true,
        onSubmit: (event) => {
          event.preventDefault();
          if (!busy) onSubmit?.(event);
        },
      }
    : {};

  return (
    <div
      className="ws-drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose?.();
      }}
    >
      <Container
        ref={panelRef}
        className={`ws-drawer ${wide ? 'ws-drawer--wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        {...containerProps}
      >
        <header className="ws-drawer__head">
          <div style={{ minWidth: 0 }}>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button type="button" className="ws-icon-btn" onClick={onClose} disabled={busy} aria-label="Đóng" title="Đóng (Esc)">
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </header>
        <div className="ws-drawer__body">{children}</div>
        {footer && <footer className="ws-drawer__foot">{footer}</footer>}
      </Container>
    </div>
  );
}

export default Drawer;
