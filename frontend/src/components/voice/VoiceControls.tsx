import { Hand, Mic, MicOff, PhoneOff, Square } from "lucide-react";
import type { VoiceUiState } from "../../voiceAssistant";

interface Props {
  state: VoiceUiState; phase: "off" | "connecting" | "on" | "ended" | "error"; muted: boolean; disabled?: boolean;
  onStart: () => void; onEnd: () => void; onMute: () => void; onInterrupt: () => void; onMic: () => void; listening: boolean;
}

export function VoiceControls({ state, phase, muted, disabled, onStart, onEnd, onMute, onInterrupt, onMic, listening }: Props) {
  if (phase === "off" || phase === "ended" || phase === "error") {
    return (
      <div className="vc">
        <button className="vc-start" onClick={onStart} disabled={disabled} data-testid="voice-start">
          <Mic size={22} aria-hidden="true" />{phase === "error" ? "Try again" : phase === "ended" ? "Start a new voice conversation" : "Start voice conversation"}
        </button>
      </div>
    );
  }
  const connecting = phase === "connecting";
  return (
    <div className="vc" role="group" aria-label="Voice controls">
      <button className={`vc-side${muted ? " on" : ""}`} onClick={onMute} aria-pressed={muted} disabled={connecting} data-testid="voice-mute">
        {muted ? <MicOff size={20} aria-hidden="true" /> : <Mic size={20} aria-hidden="true" />}<span>{muted ? "Unmute" : "Mute"}</span>
      </button>
      {state === "speaking"
        ? <button className="vc-main interrupt" onClick={onInterrupt} data-testid="voice-interrupt" aria-label="Interrupt Saathi"><Hand size={30} aria-hidden="true" /></button>
        : <button className={`vc-main${listening ? " live" : ""}`} onClick={onMic} disabled={connecting || state === "thinking"} data-testid="voice-mic"
          aria-label={listening ? "Stop listening" : "Start listening"} aria-pressed={listening}>
          {listening ? <Square size={26} aria-hidden="true" /> : <Mic size={30} aria-hidden="true" />}
        </button>}
      <button className="vc-side end" onClick={onEnd} data-testid="voice-end"><PhoneOff size={20} aria-hidden="true" /><span>End</span></button>
    </div>
  );
}
