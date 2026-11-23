import { useEffect, useMemo } from "react";
import { Activity, Droplet, Heart, HeartPulse, Leaf, Moon, Pill, Stethoscope, Sun, type LucideIcon } from "lucide-react";

/**
 * Calm wellness backdrop for a health companion: faint line icons (heart, leaf,
 * droplet, pulse...) floating gently, and a soft heartbeat line. Transform/opacity only; pointer-events none; the layers
 * lean slightly toward the cursor. Reduced-motion switches every animation off. Also feeds --mx/--my to interactive cards.
 */
const ICONS: LucideIcon[] = [Heart, Leaf, Droplet, Activity, Sun, Stethoscope, HeartPulse, Moon, Pill, Leaf, Droplet, Heart];
const rnd = (i: number, k: number) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); }; // deterministic "random"

export function Backdrop() {
  useEffect(() => {
    let raf = 0;
    const root = document.querySelector<HTMLElement>(".backdrop");
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        root?.style.setProperty("--px", ((e.clientX / innerWidth - 0.5) * 2).toFixed(3));
        root?.style.setProperty("--py", ((e.clientY / innerHeight - 0.5) * 2).toFixed(3));
        const el = (e.target as HTMLElement | null)?.closest<HTMLElement>(".qa, .pkg-card, .card.interactive, .prompt, .scenario");
        if (el) { const r = el.getBoundingClientRect(); el.style.setProperty("--mx", `${e.clientX - r.left}px`); el.style.setProperty("--my", `${e.clientY - r.top}px`); }
      });
    };
    document.addEventListener("pointermove", move, { passive: true });
    return () => { document.removeEventListener("pointermove", move); cancelAnimationFrame(raf); };
  }, []);

  const icons = useMemo(() => ICONS.map((Icon, i) => ({
    Icon, left: 3 + ((i * 8.3 + rnd(i, 1) * 6) % 92), top: 6 + ((i * 17 + rnd(i, 2) * 14) % 80), size: 30 + rnd(i, 3) * 38,
    dur: 16 + rnd(i, 4) * 14, delay: -rnd(i, 5) * 30, tilt: -14 + rnd(i, 6) * 28,
  })), []);

  return (
    <div className="backdrop" aria-hidden="true">
      <div className="bd-calm" />
      <div className="layer wellicons">
        {icons.map(({ Icon, left, top, size, dur, delay, tilt }, i) => (
          <span key={i} className="wicon" style={{ left: `${left}%`, top: `${top}%`, width: size, height: size, animationDuration: `${dur}s`, animationDelay: `${delay}s`, ["--tilt" as string]: `${tilt}deg` }}>
            <Icon size={size} strokeWidth={1.4} />
          </span>
        ))}
      </div>
      <svg className="ecg" viewBox="0 0 1600 200" preserveAspectRatio="none">
        <path className="ecg-base" d="M0 110h330l22-8 22 8h60l18-62 26 120 26-96 18 38h210l22-8 22 8h60l18-62 26 120 26-96 18 38h330" />
        <path className="ecg-run" d="M0 110h330l22-8 22 8h60l18-62 26 120 26-96 18 38h210l22-8 22 8h60l18-62 26 120 26-96 18 38h330" pathLength="100" />
      </svg>
      <div className="grain" />
    </div>
  );
}
