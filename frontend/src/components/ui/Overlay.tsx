import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, type LucideIcon } from "lucide-react";
import { Button, IconButton } from "./Button";

const FOCUSABLE = 'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])';

/** Traps Tab inside `ref`, closes on Escape, restores focus to the opener on unmount. */
function useDialogBehaviour(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const node = ref.current;
    (node?.querySelector<HTMLElement>("[data-autofocus]") ?? node?.querySelector<HTMLElement>(FOCUSABLE))?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      if (e.key !== "Tab" || !node) return;
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (items.length === 0) return;
      const first = items[0]!, last = items[items.length - 1]!;
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); opener?.focus?.(); };
  }, [open, onClose]);
  return ref;
}

interface ModalProps { open: boolean; onClose: () => void; title: string; children: ReactNode; actions?: ReactNode; icon?: LucideIcon }

export function Modal({ open, onClose, title, children, actions }: ModalProps) {
  const ref = useDialogBehaviour(open, onClose);
  const tid = useId();
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
          <motion.div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={tid}
            initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8 }} transition={{ duration: 0.2, ease: [0.22, 0.8, 0.24, 1] }}>
            <h2 id={tid}>{title}</h2>
            <div className="muted">{children}</div>
            {actions && <div className="actions">{actions}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

interface ConfirmProps { open: boolean; title: string; children: ReactNode; confirmLabel: string; cancelLabel?: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void }

export function ConfirmationDialog({ open, title, children, confirmLabel, cancelLabel = "Go back", danger, busy, onConfirm, onCancel }: ConfirmProps) {
  return (
    <Modal open={open} onClose={onCancel} title={title} actions={<>
      <Button data-autofocus variant="ghost" onClick={onCancel}>{cancelLabel}</Button>
      <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
    </>}>{children}</Modal>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useDialogBehaviour(open, onClose);
  const tid = useId();
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="drawer-wrap" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
          <motion.aside ref={ref} className="drawer" role="dialog" aria-modal="true" aria-labelledby={tid}
            initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={{ duration: 0.22, ease: [0.22, 0.8, 0.24, 1] }}>
            <div className="drawer-head"><h2 id={tid}>{title}</h2><IconButton icon={X} label="Close" onClick={onClose} /></div>
            {children}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  const id = useId();
  return <span className="tip" aria-describedby={id}>{children}<span id={id} role="tooltip">{text}</span></span>;
}

export function Dropdown({ trigger, children, label }: { trigger: (p: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu" }) => ReactNode; children: (close: () => void) => ReactNode; label: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="dropdown" ref={ref}>
      {trigger({ onClick: () => setOpen((o) => !o), "aria-expanded": open, "aria-haspopup": "menu" })}
      {open && <div className="menu" role="menu" aria-label={label}>{children(() => setOpen(false))}</div>}
    </div>
  );
}
