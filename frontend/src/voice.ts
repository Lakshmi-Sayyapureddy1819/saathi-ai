// Browser voice channel: Web Speech API for STT and TTS. Only the edge differs; the transcript goes through the
// same /messages endpoint (same safety gate, router and booking flow) as typed chat.
import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceLang = "en-IN" | "hi-IN";

interface RecognitionResult { isFinal: boolean; 0: { transcript: string } }
interface RecognitionEvent { results: ArrayLike<RecognitionResult> }
interface Recognition {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start(): void; stop(): void; abort(): void;
}
type RecognitionCtor = new () => Recognition;

const ctor = (): RecognitionCtor | null => {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

export const voiceSupported = (): boolean => ctor() !== null && "speechSynthesis" in window;

/** Plain text for the speaker: drops markdown/emoji punctuation and spells out the booking id digit by digit. */
export function toSpeakable(text: string): string {
  return text
    .replace(/[*_`#>]/g, "")
    .replace(/\p{Extended_Pictographic}/gu, "")
    .replace(/\b([A-Z]{2,}-?)(\d{3,})\b/g, (_m, p: string, d: string) => `${p.replace("-", " ")} ${d.split("").join(" ")}`)
    .replace(/\s+/g, " ")
    .trim();
}

export interface VoiceState {
  supported: boolean;
  listening: boolean;
  speaking: boolean;
  interim: string;
  lastTtfaMs: number | null; // transcript sent -> first audio of the reply
  error: string | null;
}

export function useVoice(onTranscript: (text: string) => void, lang: VoiceLang) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lastTtfaMs, setLastTtfaMs] = useState<number | null>(null);
  const rec = useRef<Recognition | null>(null);
  const sentAt = useRef<number | null>(null);
  const cb = useRef(onTranscript);
  cb.current = onTranscript;

  const stopSpeaking = useCallback(() => { window.speechSynthesis?.cancel(); setSpeaking(false); }, []);

  const listen = useCallback(() => {
    const C = ctor();
    if (!C) { setError("Speech recognition is not supported in this browser (try Chrome or Edge)."); return; }
    stopSpeaking(); // barge-in: the caller talking cuts the assistant off mid-sentence
    setError(null); setInterim("");
    const r = new C();
    r.lang = lang; r.interimResults = true; r.continuous = false;
    r.onresult = (e) => {
      let text = ""; let final = false;
      for (let i = 0; i < e.results.length; i++) { text += e.results[i][0].transcript; final = e.results[i].isFinal; }
      setInterim(text);
      if (final && text.trim()) { sentAt.current = performance.now(); cb.current(text.trim()); }
    };
    r.onerror = (e) => { if (e.error !== "no-speech" && e.error !== "aborted") setError(`Microphone error: ${e.error}`); };
    r.onend = () => { setListening(false); setInterim(""); };
    rec.current = r; setListening(true); r.start();
  }, [lang, stopSpeaking]);

  const stopListening = useCallback(() => { rec.current?.stop(); setListening(false); }, []);

  const speak = useCallback((text: string) => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(toSpeakable(text));
    u.lang = lang;
    u.onstart = () => {
      setSpeaking(true);
      if (sentAt.current !== null) { setLastTtfaMs(Math.round(performance.now() - sentAt.current)); sentAt.current = null; }
    };
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.speak(u);
  }, [lang]);

  useEffect(() => () => { rec.current?.abort(); window.speechSynthesis?.cancel(); }, []);

  const state: VoiceState = { supported: voiceSupported(), listening, speaking, interim, lastTtfaMs, error };
  return { ...state, listen, stopListening, speak, stopSpeaking };
}
