import { useEffect, useState } from "react";
import { api } from "../api";
import { formatINR } from "../format";
import type { PackageOption } from "../types";

interface Props {
  actionLabel: string;
  disabled?: boolean;
  onPick: (p: PackageOption) => void;
  compact?: boolean;
  /** When given, filters this list locally instead of calling the catalogue endpoint. */
  options?: PackageOption[];
}

/** Searchable lab-package list. Data comes from GET /api/packages (or an options list the backend asked about). */
export function PackageBrowser({ actionLabel, disabled, onPick, compact, options }: Props) {
  const [q, setQ] = useState("");
  const [remote, setRemote] = useState<PackageOption[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (options) return;
    let live = true;
    const t = setTimeout(() => {
      api.packages(q).then((r) => { if (live) { setRemote(r); setErr(null); } })
        .catch((e: Error) => { if (live) setErr(e.message); });
    }, 200);
    return () => { live = false; clearTimeout(t); };
  }, [q, options]);

  const list = options ? options.filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) ||
    p.package_id.toLowerCase().includes(q.toLowerCase())) : remote;

  return (
    <div className="pkgs">
      <label className="sr-only" htmlFor={`pkg-q-${compact ? "c" : "d"}`}>Search lab packages</label>
      <input id={`pkg-q-${compact ? "c" : "d"}`} type="search" placeholder="Search tests (e.g. thyroid, vitamin, cardiac)"
        value={q} onChange={(e) => setQ(e.target.value)} data-testid="pkg-search" />
      {err && <p className="err" role="alert">{err}</p>}
      {list === null && !err && <p className="muted">Loading packages…</p>}
      {list !== null && list.length === 0 && <p className="muted" data-testid="pkg-empty">No packages match “{q}”.</p>}
      <ul className="pkg-list" data-testid="pkg-list">
        {list?.map((p) => (
          <li key={p.package_id}>
            <div>
              <strong>{p.name}</strong>
              <span className="muted"> {p.package_id} · {p.test_count} tests · {formatINR(p.price_inr)}
                {p.fasting_required ? ` · fasting ${p.fasting_hours}h` : ""}</span>
            </div>
            <button className="btn small" disabled={disabled} onClick={() => onPick(p)}
              aria-label={`${actionLabel} ${p.name}`}>{actionLabel}</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
