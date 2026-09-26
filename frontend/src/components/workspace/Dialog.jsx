import { useCallback, useEffect, useRef, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faXmark } from '@fortawesome/free-solid-svg-icons';

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Hộp thoại dùng chung: đóng bằng Esc hoặc bấm nền (khi không bận), khoá cuộn trang,
 * đưa focus vào phần tử đầu tiên và trả focus về chỗ cũ khi đóng.
 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  busy = false,
  wide = false,
  children,
  footer,
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
    const focusTimer = window.setTimeout(() => {
      const target = panelRef.current?.querySelector('[data-autofocus]')
        || panelRef.current?.querySelector(`.ws-dialog__body ${FOCUSABLE}`)
        || panelRef.current?.querySelector(FOCUSABLE);
      target?.focus();
    }, 30);
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busyRef.current) {
        event.stopPropagation();
        onCloseRef.current?.();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, [open]);

  if (!open) return null;

  const containerProps = Container === 'form'
    ? {
        onSubmit: (event) => {
          event.preventDefault();
          if (!busy) onSubmit?.(event);
        },
        noValidate: true,
      }
    : {};

  return (
    <div
      className="ws-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose?.();
      }}
    >
      <Container
        ref={panelRef}
        className={`ws-dialog ${wide ? 'ws-dialog--wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        {...containerProps}
      >
        <div className="ws-dialog__head">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button type="button" className="ws-icon-btn" onClick={onClose} disabled={busy} aria-label="Đóng">
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>
        <div className="ws-dialog__body">{children}</div>
        {footer && <div className="ws-dialog__foot">{footer}</div>}
      </Container>
    </div>
  );
}

/**
 * Thay window.confirm bằng hộp thoại trong trang.
 * const [confirm, confirmDialog] = useConfirm();
 * if (!(await confirm({ title, description, confirmLabel, tone: 'danger' }))) return;
 */
export function useConfirm() {
  const [request, setRequest] = useState(null);

  const confirm = useCallback((options) => new Promise((resolve) => {
    setRequest({ ...options, resolve });
  }), []);

  const settle = (value) => {
    request?.resolve(value);
    setRequest(null);
  };

  const dialog = (
    <Dialog
      open={Boolean(request)}
      title={request?.title || 'Xác nhận thao tác'}
      description={request?.description}
      onClose={() => settle(false)}
      footer={(
        <>
          <button type="button" className="btn btn--outline" onClick={() => settle(false)}>
            {request?.cancelLabel || 'Huỷ'}
          </button>
          <button
            type="button"
            data-autofocus
            className={`btn ${request?.tone === 'danger' ? 'btn--danger' : 'btn--primary'}`}
            onClick={() => settle(true)}
          >
            {request?.confirmLabel || 'Xác nhận'}
          </button>
        </>
      )}
    >
      {request?.body || null}
    </Dialog>
  );

  return [confirm, dialog];
}

/**
 * Thông báo ngắn trong trang (thay window.alert). Thông báo thành công tự ẩn sau 5 giây.
 */
export function useFlash() {
  const [flash, setFlash] = useState(null);
  const timerRef = useRef(null);

  const clear = useCallback(() => {
    window.clearTimeout(timerRef.current);
    setFlash(null);
  }, []);

  const show = useCallback((tone, message) => {
    window.clearTimeout(timerRef.current);
    setFlash({ tone, message, id: Date.now() });
    if (tone === 'success' || tone === 'info') {
      timerRef.current = window.setTimeout(() => setFlash(null), 5000);
    }
  }, []);

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  return { flash, show, clear };
}
