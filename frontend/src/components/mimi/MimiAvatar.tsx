import { useEffect, useRef, useState, type MutableRefObject } from "react";
import mimiGif from "../../assets/mimi.gif";

export type MimiState = "idle" | "listening" | "thinking" | "speaking" | "success" | "error";

export const MIMI_LABEL: Record<MimiState, string> = {
  idle: "Mimi is relaxed", listening: "Mimi is listening", thinking: "Mimi is thinking",
  speaking: "Mimi is speaking", success: "Mimi is happy", error: "Mimi is confused",
};

interface Props {
  state?: MimiState;
  size?: number;
  /** Show a still frame instead of the animation (older chat messages keep the page light). */
  still?: boolean;
  /** Real microphone level 0..1 (listening only). Never invented: omit it and Mimi simply doesn't react to sound. */
  level?: MutableRefObject<number>;
  /**
   * Real word-boundary signal from speechSynthesis (0..1 per spoken word, decayed here). While words keep arriving, Mimi pulses
   * with them (data-lip="live"); when none arrive she uses a state-driven speaking pulse (data-lip="loop"). It is NOT audio amplitude.
   */
  mouth?: MutableRefObject<number>;
  decorative?: boolean;
  className?: string;
}

// First frame of the GIF, drawn once to a canvas. Used for `still` and for prefers-reduced-motion (a GIF ignores CSS).
let stillPromise: Promise<string> | null = null;
function stillFrame(): Promise<string> {
  stillPromise ??= new Promise<string>((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext("2d")!.drawImage(img, 0, 0); resolve(c.toDataURL("image/png"));
      } catch { resolve(mimiGif); }
    };
    img.onerror = () => resolve(mimiGif);
    img.src = mimiGif;
  });
  return stillPromise;
}

function usePrefersReducedMotion(): boolean {
  const [r, setR] = useState(() => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const m = matchMedia("(prefers-reduced-motion: reduce)"); const f = () => setR(m.matches);
    m.addEventListener("change", f); return () => m.removeEventListener("change", f);
  }, []);
  return r;
}

const Star = () => <svg viewBox="-8 -8 16 16" width="100%" height="100%" aria-hidden="true"><path d="M0-7Q1.200-1.200 7 0Q1.200 1.200 0 7Q-1.200 1.200-7 0Q-1.200-1.200 0-7Z" fill="currentColor" /></svg>;

/** Mimi, the Saathi Care companion: the supplied cloud-mascot GIF, with state effects drawn around it. */
export function MimiAvatar({ state = "idle", size = 120, still, level, mouth, decorative = true, className = "" }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();
  const frozen = !!still || reduced;
  const [poster, setPoster] = useState<string | null>(null);
  useEffect(() => { if (frozen) void stillFrame().then(setPoster); }, [frozen]);

  const reactive = !!level && !frozen && state === "listening";
  useEffect(() => {
    const el = root.current; if (!el) return;
    if (!reactive) { el.style.setProperty("--lvl", "0"); return; }
    let id = 0;
    const loop = () => { el.style.setProperty("--lvl", level!.current.toFixed(3)); id = requestAnimationFrame(loop); };
    loop();
    return () => cancelAnimationFrame(id);
  }, [reactive, level]);

  useEffect(() => {
    const el = root.current; if (!el) return;
    if (!mouth || frozen || state !== "speaking") { el.setAttribute("data-lip", "loop"); el.style.setProperty("--mouth", "0"); return; }
    let id = 0; let last = 0; let cur = 0;
    const loop = (now: number) => {
      const v = mouth.current; mouth.current = 0;
      cur = Math.max(v, cur * 0.84); // quick attack on each word, ~100 ms release
      if (v > 0) last = now;
      el.style.setProperty("--mouth", cur.toFixed(3));
      el.setAttribute("data-lip", now - last < 900 && last > 0 ? "live" : "loop");
      id = requestAnimationFrame(loop);
    };
    id = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(id);
  }, [mouth, frozen, state]);

  return (
    <div ref={root} className={`mimi ${frozen ? "still" : ""} ${reactive ? "reactive" : ""} ${className}`} data-state={state} data-testid="mimi"
      style={{ width: size, height: size }} role={decorative ? undefined : "img"} aria-hidden={decorative || undefined} aria-label={decorative ? undefined : MIMI_LABEL[state]}>
      <i className="mg-aura" />
      <div className="mg-waves"><b /><b /><b /><b /></div>
      <div className="mg-body">
        <img src={frozen && poster ? poster : mimiGif} alt="" draggable={false} />
      </div>
      <div className="mg-orbit">{[0, 1, 2].map((i) => <span key={i} className={`mg-star s${i}`}><Star /></span>)}</div>
      <div className="mg-confetti">{[0, 1, 2, 3, 4, 5].map((i) => <span key={i} className={`mg-bit b${i}`}><Star /></span>)}</div>
      <span className="mg-q" aria-hidden="true">?</span>
    </div>
  );
}
