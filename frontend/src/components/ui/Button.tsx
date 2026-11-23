import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2, type LucideIcon } from "lucide-react";

type Variant = "default" | "primary" | "soft" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant; size?: Size; block?: boolean; loading?: boolean; icon?: LucideIcon; children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "md", block, loading, icon: Icon, children, className = "", disabled, type = "button", ...rest }, ref,
) {
  const cls = ["btn", variant === "default" ? "" : variant, size === "md" ? "" : size, block ? "block" : "", className].filter(Boolean).join(" ");
  return (
    <button ref={ref} type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Loader2 size={16} className="spin" aria-hidden="true" /> : Icon ? <Icon size={size === "sm" ? 14 : 17} aria-hidden="true" /> : null}
      {children}
    </button>
  );
});

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon; label: string; bordered?: boolean; on?: boolean; small?: boolean;
}

/** Icon-only button. `label` is mandatory: it becomes the accessible name and the native tooltip. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon: Icon, label, bordered, on, small, className = "", type = "button", ...rest }, ref,
) {
  const cls = ["icon-btn", bordered ? "bordered" : "", on ? "on" : "", small ? "sm" : "", className].filter(Boolean).join(" ");
  return (
    <button ref={ref} type={type} className={cls} aria-label={label} title={label} {...rest}>
      <Icon size={small ? 16 : 19} aria-hidden="true" />
    </button>
  );
});
