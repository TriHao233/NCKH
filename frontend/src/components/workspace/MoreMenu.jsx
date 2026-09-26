import { useEffect, useId, useRef, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronDown, faEllipsis } from '@fortawesome/free-solid-svg-icons';

/**
 * Menu "Thêm" cho các hành động phụ.
 * items: [{ key, label, icon, onClick, disabled, title, danger, divider }]
 * variant 'button' hiện chữ "Thêm", 'icon' chỉ hiện dấu ba chấm (dùng cho từng dòng bảng).
 */
function MoreMenu({ items, label = 'Thêm', variant = 'button', align = 'right', disabled = false }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const handleClick = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    const handleKey = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setOpen(false);
        rootRef.current?.querySelector('[data-menu-trigger]')?.focus();
      }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const buttons = [...(rootRef.current?.querySelectorAll('[role="menuitem"]:not([disabled])') || [])];
        if (!buttons.length) return;
        const index = buttons.indexOf(document.activeElement);
        const next = event.key === 'ArrowDown'
          ? buttons[(index + 1) % buttons.length]
          : buttons[(index - 1 + buttons.length) % buttons.length];
        next.focus();
      }
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    const first = rootRef.current?.querySelector('[role="menuitem"]:not([disabled])');
    first?.focus();
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const visibleItems = items.filter(Boolean);

  return (
    <div className="ws-more" ref={rootRef}>
      {variant === 'icon' ? (
        <button
          type="button"
          data-menu-trigger
          className="ws-icon-btn"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={menuId}
          aria-label={label}
          title={label}
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            setOpen((value) => !value);
          }}
        >
          <FontAwesomeIcon icon={faEllipsis} />
        </button>
      ) : (
        <button
          type="button"
          data-menu-trigger
          className="btn btn--outline"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={menuId}
          disabled={disabled}
          onClick={() => setOpen((value) => !value)}
        >
          {label}
          <FontAwesomeIcon icon={faChevronDown} />
        </button>
      )}
      {open && (
        <div className={`ws-more__menu ws-more__menu--${align}`} role="menu" id={menuId}>
          {visibleItems.map((item) => (item.divider ? (
            <hr key={item.key} className="ws-more__divider" />
          ) : (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              className={item.danger ? 'is-danger' : ''}
              disabled={item.disabled}
              title={item.title}
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                item.onClick?.();
              }}
            >
              {item.icon && <FontAwesomeIcon icon={item.icon} />}
              <span>{item.label}</span>
            </button>
          )))}
        </div>
      )}
    </div>
  );
}

export default MoreMenu;
