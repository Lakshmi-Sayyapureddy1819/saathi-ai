// Browser voice channel: Web Speech API for STT and TTS. Only the edge differs; the transcript goes through the
// same /messages endpoint (same safety gate, router and booking flow) as typed chat.
import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceLang = "en-IN" | "hi-IN";

interface RecognitionResult { isFinal: boolean; 0: { transcript: string; confidence?: number } }
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
    .replace(/\s?\[[A-Za-z][A-Za-z0-9_]{2,40}\]/g, "") // citation markers are shown, not read aloud
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

export const dictationSupported = (): boolean => ctor() !== null;

/** Speech-to-text only: streams what the user says into `onText` (interim and final) with auto-send on pause. */
export function useDictation(onText: (text: string, final: boolean) => void, lang: VoiceLang) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const silenceTimer = useRef<number | null>(null);
  const latestText = useRef<string>("");
  const dispatched = useRef<boolean>(false);
  const cb = useRef(onText);
  cb.current = onText;

  const dispatchFinal = useCallback(() => {
    if (silenceTimer.current !== null) {
      window.clearTimeout(silenceTimer.current);
      silenceTimer.current = null;
    }
    const txt = latestText.current.trim();
    const isSingleFiller = /^(like|uh|um|er|ah|a|the|so|well)\s*$/i.test(txt);
    if (txt && !isSingleFiller && !dispatched.current) {
      dispatched.current = true;
      cb.current(txt, true);
      try { rec.current?.stop(); } catch { /* ignore */ }
    }
  }, []);

  const start = useCallback(() => {
    const C = ctor();
    if (!C) { setError("Speech recognition is not supported in this browser (try Chrome or Edge)."); return; }
    setError(null);
    latestText.current = "";
    dispatched.current = false;
    if (silenceTimer.current !== null) {
      window.clearTimeout(silenceTimer.current);
      silenceTimer.current = null;
    }

    const r = new C();
    r.lang = lang; r.interimResults = true; r.continuous = true;
    r.onresult = (e) => {
      let accumulated = "";
      for (let i = 0; i < e.results.length; i++) {
        accumulated += e.results[i][0].transcript + " ";
      }
      const trimmed = accumulated.trim();
      latestText.current = trimmed;
      cb.current(trimmed, false);

      if (silenceTimer.current !== null) {
        window.clearTimeout(silenceTimer.current);
        silenceTimer.current = null;
      }

      // Natural conversational pause detection: 750ms of real pause before auto-dispatching
      if (trimmed) {
        silenceTimer.current = window.setTimeout(() => {
          dispatchFinal();
        }, 750);
      }
    };
    r.onerror = (e) => {
      if (silenceTimer.current !== null) { window.clearTimeout(silenceTimer.current); silenceTimer.current = null; }
      if (e.error === "not-allowed") setError("Microphone permission denied. Allow mic access in the browser address bar.");
      else if (e.error !== "no-speech" && e.error !== "aborted") setError(`Microphone error: ${e.error}`);
    };
    r.onend = () => {
      dispatchFinal();
      setListening(false);
    };
    rec.current = r; setListening(true); r.start();
  }, [lang, dispatchFinal]);

  const stop = useCallback(() => {
    if (silenceTimer.current !== null) { window.clearTimeout(silenceTimer.current); silenceTimer.current = null; }
    dispatchFinal();
    rec.current?.stop();
    setListening(false);
  }, [dispatchFinal]);

  useEffect(() => () => {
    if (silenceTimer.current !== null) window.clearTimeout(silenceTimer.current);
    rec.current?.abort();
  }, []);

  return { listening, error, start, stop, supported: dictationSupported() };
}

export function useVoice(
  onTranscript: (text: string) => void,
  lang: VoiceLang,
  onSpeakingComplete?: () => void
) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lastTtfaMs, setLastTtfaMs] = useState<number | null>(null);
  const rec = useRef<Recognition | null>(null);
  const sentAt = useRef<number | null>(null);
  const silenceTimer = useRef<number | null>(null);
  const latestText = useRef<string>("");
  // Lip-sync signal: set to 0..1 on each REAL word-boundary event from speechSynthesis (size follows word length). It is not audio
  // amplitude (the browser exposes none); consumers decay it themselves. Stays 0 when the voice sends no boundary events.
  const mouthRef = useRef(0);
  const confidenceRef = useRef<number | null>(null); // mean engine confidence of the last transcript; null = not reported
  const dispatched = useRef<boolean>(false);
  const cb = useRef(onTranscript);
  cb.current = onTranscript;
  const onCompleteRef = useRef(onSpeakingComplete);
  onCompleteRef.current = onSpeakingComplete;

  const stopSpeaking = useCallback(() => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  const dispatchCurrent = useCallback(() => {
    if (silenceTimer.current !== null) {
      window.clearTimeout(silenceTimer.current);
      silenceTimer.current = null;
    }
    const txt = latestText.current.trim();
    const isSingleFiller = /^(like|uh|um|er|ah|a|the|so|well)\s*$/i.test(txt);
    if (txt && !isSingleFiller && !dispatched.current) {
      dispatched.current = true;
      sentAt.current = performance.now();
      setInterim("");
      try { rec.current?.stop(); } catch { /* ignore */ }
      cb.current(txt);
    }
  }, []);

  const listen = useCallback(() => {
    const C = ctor();
    if (!C) { setError("Speech recognition is not supported in this browser (try Chrome or Edge)."); return; }
    stopSpeaking(); // barge-in: talking cuts the assistant off immediately
    setError(null);
    setInterim("");
    latestText.current = "";
    dispatched.current = false;

    if (silenceTimer.current !== null) {
      window.clearTimeout(silenceTimer.current);
      silenceTimer.current = null;
    }

    try { rec.current?.abort(); } catch { /* ignore */ }

    const r = new C();
    r.lang = lang;
    r.interimResults = true;
    r.continuous = true;

    r.onresult = (e) => {
      let accumulated = "";
      for (let i = 0; i < e.results.length; i++) {
        accumulated += e.results[i][0].transcript + " ";
      }
      const trimmed = accumulated.trim();
      latestText.current = trimmed;
      const confs = Array.from(e.results, (res) => res[0].confidence ?? 0).filter((c) => c > 0);
      confidenceRef.current = confs.length ? confs.reduce((a, b) => a + b, 0) / confs.length : 0.95;
      setInterim(trimmed);

      if (silenceTimer.current !== null) {
        window.clearTimeout(silenceTimer.current);
        silenceTimer.current = null;
      }

      // Natural conversational pause detection: 750ms of real pause before auto-dispatching
      if (trimmed) {
        silenceTimer.current = window.setTimeout(() => {
          dispatchCurrent();
        }, 750);
      }
    };

    r.onerror = (e) => {
      if (silenceTimer.current !== null) {
        window.clearTimeout(silenceTimer.current);
        silenceTimer.current = null;
      }
      if (e.error !== "no-speech" && e.error !== "aborted") {
        setError(`Microphone error: ${e.error}`);
      }
    };

    r.onend = () => {
      dispatchCurrent();
      setListening(false);
      setInterim("");
    };

    rec.current = r;
    setListening(true);
    try {
      r.start();
    } catch {
      setListening(false);
    }
  }, [lang, stopSpeaking, dispatchCurrent]);

  const stopListening = useCallback(() => {
    if (silenceTimer.current !== null) {
      window.clearTimeout(silenceTimer.current);
      silenceTimer.current = null;
    }
    latestText.current = "";
    dispatched.current = true;
    try { rec.current?.stop(); } catch { /* ignore */ }
    setListening(false);
  }, []);

  const speak = useCallback((text: string, onDone?: () => void) => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel();
    const clean = toSpeakable(text);
    if (!clean) return;

    // Split text into sentence chunks to minimize TTFA (Time-To-First-Audio).
    // The browser synthesizes sentence 1 immediately (<100ms) and queues the rest.
    const sentences = clean.match(/[^.!?\n]+[.!?\n]*/g)?.map((s) => s.trim()).filter(Boolean) ?? [clean];
    if (sentences.length === 0) return;

    sentences.forEach((chunk, idx) => {
      const u = new SpeechSynthesisUtterance(chunk);
      u.lang = lang;
      u.onboundary = (e: SpeechSynthesisEvent) => { if (!e.name || e.name === "word") mouthRef.current = Math.min(1, 0.45 + (e.charLength || 5) / 9); };
      u.rate = 1.15; // Brisk, energetic, and natural speech speed
      if (idx === 0) {
        u.onstart = () => {
          setSpeaking(true);
          if (sentAt.current !== null) {
            setLastTtfaMs(Math.round(performance.now() - sentAt.current));
            sentAt.current = null;
          }
        };
      }
      if (idx === sentences.length - 1) {
        u.onend = () => {
          setSpeaking(false);
          onDone?.();
          onCompleteRef.current?.();
        };
        u.onerror = () => {
          setSpeaking(false);
          onDone?.();
          onCompleteRef.current?.();
        };
      }
      synth.speak(u);
    });
  }, [lang]);

  useEffect(() => () => {
    if (silenceTimer.current !== null) { window.clearTimeout(silenceTimer.current); }
    rec.current?.abort();
    window.speechSynthesis?.cancel();
  }, []);

  const state: VoiceState = { supported: voiceSupported(), listening, speaking, interim, lastTtfaMs, error };
  return { ...state, listen, stopListening, speak, stopSpeaking, confidenceRef, mouthRef };
}

const TIMEISH = /\d|\b(baje|bajke|subah|shaam|dopahar|raat|am|pm|o.?clock|morning|evening|noon|kal|aaj|parso|today|tomorrow)\b/i;
const CLEAR_YES = /^(yes|yeah|yep|haan ji|haan|han|ha|ji haan|ok|okay|sure|confirm|theek hai|thik hai)\b/i;

/**
 * Booking safety for voice: should this transcript be shown to the user for a tap-to-confirm before it is sent?
 * - confirming stage: only a clear, confident "yes" goes straight through; everything else (incl. low confidence) is held.
 * - slot stage: any time/date/number-like speech with unknown or low confidence is held.
 * - any booking stage: very low confidence is held.
 * Outside a booking nothing is held (a misheard wellness question is harmless; the safety gate still runs).
 */
export function needsReview(text: string, confidence: number | null, stage: "idle" | "choosing_package" | "choosing_slot" | "confirming"): boolean {
  if (stage === "idle") return false;
  const low = confidence !== null && confidence < 0.8;
  if (stage === "confirming") return !(CLEAR_YES.test(text.trim()) && !low && confidence !== null);
  if (stage === "choosing_slot" && TIMEISH.test(text)) return confidence === null || low;
  return confidence !== null && confidence < 0.6;
}
