import { useId, type KeyboardEvent, type ReactNode } from "react";

export interface TabDef<T extends string> { id: T; label: string; count?: number }

/** Segmented control with the WAI-ARIA tabs pattern (arrow keys move between tabs). */
export function Tabs<T extends string>({ tabs, value, onChange, label, children }: { tabs: TabDef<T>[]; value: T; onChange: (id: T) => void; label: string; children?: ReactNode }) {
  const uid = useId();
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = tabs.findIndex((t) => t.id === value);
    const n = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i - 1 + tabs.length) % tabs.length : -1;
    if (n >= 0) { e.preventDefault(); onChange(tabs[n]!.id); document.getElementById(`${uid}-${tabs[n]!.id}`)?.focus(); }
  };
  return (
    <>
      <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
        {tabs.map((t) => (
          <button key={t.id} id={`${uid}-${t.id}`} role="tab" aria-selected={t.id === value} tabIndex={t.id === value ? 0 : -1} onClick={() => onChange(t.id)}>
            {t.label}{t.count !== undefined && t.count > 0 && <span className="count">{t.count}</span>}
          </button>
        ))}
      </div>
      {children && <div role="tabpanel" aria-labelledby={`${uid}-${value}`}>{children}</div>}
    </>
  );
}
