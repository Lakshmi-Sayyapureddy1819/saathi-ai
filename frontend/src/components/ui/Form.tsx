import { forwardRef, useId, type InputHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from "react";
import { Search } from "lucide-react";

interface FieldProps { label: string; help?: ReactNode; error?: string | null; hideLabel?: boolean }

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & FieldProps>(function Input(
  { label, help, error, hideLabel, id, className = "", ...rest }, ref,
) {
  const auto = useId(); const fid = id ?? auto;
  return (
    <div className="field">
      <label htmlFor={fid} className={hideLabel ? "sr-only" : undefined}>{label}</label>
      <input ref={ref} id={fid} className={`input ${className}`} aria-invalid={!!error} aria-describedby={error || help ? `${fid}-h` : undefined} {...rest} />
      {(error || help) && <span id={`${fid}-h`} className={`help${error ? " err" : ""}`}>{error ?? help}</span>}
    </div>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & FieldProps>(function Textarea(
  { label, help, error, hideLabel, id, className = "", ...rest }, ref,
) {
  const auto = useId(); const fid = id ?? auto;
  return (
    <div className="field">
      <label htmlFor={fid} className={hideLabel ? "sr-only" : undefined}>{label}</label>
      <textarea ref={ref} id={fid} className={`textarea ${className}`} aria-invalid={!!error} aria-describedby={error || help ? `${fid}-h` : undefined} {...rest} />
      {(error || help) && <span id={`${fid}-h`} className={`help${error ? " err" : ""}`}>{error ?? help}</span>}
    </div>
  );
});

interface SearchBarProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
  value: string; onChange: (v: string) => void; label: string;
}

export function SearchBar({ value, onChange, label, ...rest }: SearchBarProps) {
  return (
    <label className="search">
      <span className="sr-only">{label}</span>
      <Search size={18} aria-hidden="true" />
      <input type="search" className="input" value={value} onChange={(e) => onChange(e.target.value)} placeholder={label} {...rest} />
    </label>
  );
}
