import { Fragment, type CSSProperties, type HTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Clock, Info, OctagonAlert, XCircle, type LucideIcon } from "lucide-react";

export function Card({ interactive, flat, className = "", ...rest }: HTMLAttributes<HTMLDivElement> & { interactive?: boolean; flat?: boolean }) {
  return <div className={["card", interactive ? "interactive" : "", flat ? "flat" : "", className].filter(Boolean).join(" ")} {...rest} />;
}

export type Tone = "neutral" | "success" | "info" | "warn" | "danger" | "brand";
const TONE_ICON: Record<Tone, LucideIcon | null> = { neutral: null, brand: null, success: CheckCircle2, info: Info, warn: Clock, danger: OctagonAlert };

/** Status is always icon + text, never colour alone. */
export function StatusBadge({ tone = "neutral", children, icon, ...rest }: { tone?: Tone; children: ReactNode; icon?: LucideIcon | false } & HTMLAttributes<HTMLSpanElement>) {
  const Icon = icon === false ? null : icon ?? TONE_ICON[tone];
  return <span className={`badge ${tone}`} {...rest}>{Icon && <Icon size={13} aria-hidden="true" />}{children}</span>;
}

export function Avatar({ name, size, brand }: { name: string; size?: "sm" | "lg"; brand?: boolean }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "S";
  return <span className={`avatar${size ? ` ${size}` : ""}${brand ? " brand" : ""}`} aria-hidden="true">{initials}</span>;
}

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: string; title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{actions}</div>}
    </header>
  );
}

export function EmptyState({ icon: Icon, title, text, action, ...rest }: { icon: LucideIcon; title: string; text?: ReactNode; action?: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className="empty-state" {...rest}>
      <span className="ic"><Icon size={26} aria-hidden="true" /></span>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ w = "100%", h = 16, style }: { w?: number | string; h?: number | string; style?: CSSProperties }) {
  return <span className="skeleton" aria-hidden="true" style={{ width: w, height: h, ...style }} />;
}

const BANNER_ICON = { info: Info, warn: AlertTriangle, err: XCircle, ok: CheckCircle2 } as const;
export function Banner({ tone = "info", children, action, ...rest }: { tone?: keyof typeof BANNER_ICON; children: ReactNode; action?: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  const Icon = BANNER_ICON[tone];
  return <div className={`banner ${tone}`} {...rest}><Icon size={17} aria-hidden="true" /><div className="grow">{children}</div>{action}</div>;
}

export function KeyValue({ rows }: { rows: [string, ReactNode][] }) {
  return <dl className="kv">{rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>;
}
