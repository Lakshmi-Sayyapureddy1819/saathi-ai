import { useEffect, useRef, type MutableRefObject, type ReactNode } from "react";
import { AlertTriangle, Check } from "lucide-react";
import type { VoiceUiState } from "../../voiceAssistant";

const BARS = 9;

/**
 * Central orb. Visuals per state are pure CSS (see voice.css). The only data-driven motion is `--lvl`, written
 * straight to the DOM from the real microphone level while listening, with no React re-renders. If no level is
 * available (`levelAvailable` false) the orb simply doesn't react to sound.
 */
export function VoiceOrb({ state, level, levelAvailable, children }: { state: VoiceUiState; level: MutableRefObject<number>; levelAvailable: boolean; children?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    if (state !== "listening" || !levelAvailable) { el.style.setProperty("--lvl", "0"); return; }
    let id = 0;
    const loop = () => { el.style.setProperty("--lvl", level.current.toFixed(3)); id = requestAnimationFrame(loop); };
    loop();
    return () => cancelAnimationFrame(id);
  }, [state, level, levelAvailable]);

  return (
    <div ref={ref} className={`orb orb-${state}${levelAvailable ? " has-level" : ""}${children ? " with-mascot" : ""}`} data-state={state} data-testid="voice-orb" aria-hidden="true">
      <i className="ring r1" /><i className="ring r2" /><i className="ring r3" />
      <div className="core">
        {children}
        <div className="bars">{Array.from({ length: BARS }, (_, i) => <b key={i} style={{ ["--i" as string]: i }} />)}</div>
        {state === "error" && <AlertTriangle className="core-ic" size={46} />}
        {state === "ended" && <Check className="core-ic" size={46} />}
      </div>
    </div>
  );
}
