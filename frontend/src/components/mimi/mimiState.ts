import type { VoiceUiState } from "../../voiceAssistant";
import type { MimiState } from "./MimiAvatar";

/**
 * Maps the real voice lifecycle to Mimi's expression. `celebrate` is true for a short moment after the backend
 * confirms a booking (and the reply has finished being spoken); `error` always wins so problems are never hidden.
 */
export function mimiFromVoice(state: VoiceUiState, celebrate: boolean): MimiState {
  if (state === "error") return "error";
  if (state === "speaking") return "speaking"; // lips sync while words are spoken, celebration waits until speech ends
  if (celebrate) return "success";
  if (state === "listening" || state === "interrupted") return "listening";
  if (state === "thinking" || state === "processing" || state === "connecting") return "thinking";
  return "idle";
}
