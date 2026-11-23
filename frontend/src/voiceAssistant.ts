// State machine for the immersive voice screen. Wraps the browser speech hooks in voice.ts; nothing here fakes audio.
// - Orb "level" is the real microphone RMS from an AnalyserNode. If that is unavailable we say so and show no level.
// - Speaking animation is driven by the real speechSynthesis `speaking` flag (the browser gives no output amplitude).
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { api } from "./api";
import { needsReview, useVoice, voiceSupported, type VoiceLang } from "./voice";
import type { SessionView } from "./types";

export type VoiceUiState = "idle" | "connecting" | "listening" | "processing" | "thinking" | "speaking" | "interrupted" | "error" | "ended";
export type VoiceErrorKind = "unsupported" | "denied" | "no-device" | "network" | "speech" | null;

export const STATE_COPY: Record<VoiceUiState, { label: string; hint: string }> = {
  idle: { label: "Ready to listen", hint: "Tap the microphone to start talking to Saathi." },
  connecting: { label: "Connecting", hint: "Checking the microphone and the Saathi server." },
  listening: { label: "Listening", hint: "Go ahead, I'm listening. Pause when you're done." },
  processing: { label: "Processing", hint: "Making sure I understood you correctly." },
  thinking: { label: "Thinking", hint: "Saathi is preparing a reply." },
  speaking: { label: "Speaking", hint: "Saathi is speaking. Tap Interrupt to cut in." },
  interrupted: { label: "Interrupted", hint: "Okay, I stopped. Go ahead." },
  error: { label: "Something went wrong", hint: "Read the message for how to fix it." },
  ended: { label: "Conversation ended", hint: "You can start again or return to chat." },
};

export const ERROR_COPY: Record<Exclude<VoiceErrorKind, null>, { title: string; fix: string }> = {
  unsupported: { title: "Voice isn't supported in this browser", fix: "Open Saathi in Chrome or Edge on desktop or Android, or use the text chat instead." },
  denied: { title: "Microphone access was blocked", fix: "Click the lock icon in the address bar, allow the microphone for this site, then press Try again." },
  "no-device": { title: "No microphone found", fix: "Connect or enable a microphone, check your system sound settings, then press Try again." },
  network: { title: "Can't reach the speech or Saathi service", fix: "Check your internet connection and that the Saathi server is running, then press Try again." },
  speech: { title: "Speech recognition stopped", fix: "Press Try again. If it keeps happening, use the text chat." },
};

interface Args {
  session: SessionView;
  busy: boolean;
  paused: boolean;
  lang: VoiceLang;
  send: (text: string, channel: "web" | "voice") => Promise<void> | void;
}

export interface Review { text: string; confidence: number | null }

export function useVoiceAssistant({ session, busy, paused, lang, send }: Args) {
  const [phase, setPhase] = useState<"off" | "connecting" | "on" | "ended" | "error">("off");
  const [errorKind, setErrorKind] = useState<VoiceErrorKind>(null);
  const [muted, setMuted] = useState(false);
  const [review, setReview] = useState<Review | null>(null);
  const [processing, setProcessing] = useState(false);
  const [interrupted, setInterrupted] = useState(false);
  const [levelAvailable, setLevelAvailable] = useState(false);
  const [startIndex, setStartIndex] = useState(0);
  const level: MutableRefObject<number> = useRef(0);
  const stream = useRef<MediaStream | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const raf = useRef<number | null>(null);
  const spoken = useRef(session.messages.length);
  const stageRef = useRef(session.booking.stage);
  stageRef.current = session.booking.stage;
  const staleErr = useRef<string | null>(null); // a speech error left over from a previous attempt must not re-trigger
  const sendRef = useRef(send);
  sendRef.current = send;

  const submit = useCallback((text: string) => {
    setReview(null); setProcessing(true);
    void sendRef.current(text, "voice");
  }, []);

  const voiceRef = useRef<ReturnType<typeof useVoice> | null>(null);
  const voice = useVoice((text) => {
    const conf = voiceRef.current?.confidenceRef.current ?? null;
    if (needsReview(text, conf, stageRef.current)) { setReview({ text, confidence: conf }); setProcessing(false); }
    else submit(text);
  }, lang);
  voiceRef.current = voice;

  const lastAssistant = [...session.messages].reverse().find((m) => m.role === "assistant");
  const halted = lastAssistant?.kind === "emergency"; // after emergency guidance we do not auto-listen; the user chooses

  const stopMeter = useCallback(() => {
    if (raf.current !== null) cancelAnimationFrame(raf.current);
    raf.current = null; level.current = 0;
    stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null;
    void audioCtx.current?.close().catch(() => undefined); audioCtx.current = null;
    setLevelAvailable(false);
  }, []);

  const fail = useCallback((k: Exclude<VoiceErrorKind, null>) => {
    voiceRef.current?.stopListening(); voiceRef.current?.stopSpeaking(); stopMeter();
    setErrorKind(k); setPhase("error"); setProcessing(false);
  }, [stopMeter]);

  const start = useCallback(async () => {
    if (!voiceSupported()) { fail("unsupported"); return; }
    staleErr.current = voiceRef.current?.error ?? null;
    setErrorKind(null); setPhase("connecting"); setMuted(false); setReview(null); setProcessing(false); setInterrupted(false);
    try { await api.config(); } catch { fail("network"); return; }
    if (!navigator.mediaDevices?.getUserMedia) { fail("no-device"); return; }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException).name;
      fail(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "no-device");
      return;
    }
    try { // real input level; failure only disables the level display
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctx && stream.current) {
        const ctx = new Ctx(); audioCtx.current = ctx;
        const an = ctx.createAnalyser(); an.fftSize = 256;
        ctx.createMediaStreamSource(stream.current).connect(an);
        const buf = new Uint8Array(an.fftSize);
        const tick = () => {
          an.getByteTimeDomainData(buf);
          let sum = 0; for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
          level.current = level.current * 0.7 + Math.min(1, Math.sqrt(sum / buf.length) * 4) * 0.3;
          raf.current = requestAnimationFrame(tick);
        };
        tick(); setLevelAvailable(true);
      }
    } catch { setLevelAvailable(false); }
    setStartIndex(session.messages.length); spoken.current = session.messages.length;
    setPhase("on");
  }, [fail, session.messages.length]);

  const end = useCallback(() => {
    voiceRef.current?.stopListening(); voiceRef.current?.stopSpeaking(); stopMeter();
    setReview(null); setProcessing(false); setInterrupted(false); setPhase("ended");
  }, [stopMeter]);

  const toggleMute = useCallback(() => {
    setMuted((m) => { if (!m) voiceRef.current?.stopListening(); return !m; });
  }, []);

  const interrupt = useCallback(() => {
    voiceRef.current?.stopSpeaking(); setInterrupted(true);
    window.setTimeout(() => setInterrupted(false), 1200);
  }, []);

  const micTap = useCallback(() => {
    const v = voiceRef.current; if (!v) return;
    if (v.listening) v.stopListening();
    else { setMuted(false); v.listen(); }
  }, []);

  const confirmReview = useCallback(() => { if (review) submit(review.text); }, [review, submit]);
  const discardReview = useCallback(() => setReview(null), []);

  useEffect(() => { if (!voice.error) staleErr.current = null; }, [voice.error]);
  // Map browser speech errors to our error kinds.
  useEffect(() => {
    if (phase !== "on" || !voice.error || voice.error === staleErr.current) return;
    const e = voice.error;
    fail(/not-allowed|service-not-allowed/.test(e) ? "denied" : /network/.test(e) ? "network" : /audio-capture/.test(e) ? "no-device" : "speech");
  }, [voice.error, phase, fail]);

  // Speak each new assistant reply; this is what the user hears.
  useEffect(() => {
    if (phase !== "on") return;
    const msgs = session.messages;
    if (msgs.length <= spoken.current) { spoken.current = msgs.length; return; }
    const fresh = msgs.slice(spoken.current); spoken.current = msgs.length;
    const last = [...fresh].reverse().find((m) => m.role === "assistant");
    if (last) { setProcessing(false); voiceRef.current?.speak(last.kind === "emergency" ? (last.emergency?.message ?? last.text) : last.text); }
  }, [session.messages, phase]);

  useEffect(() => { if (busy) setProcessing(false); }, [busy]);
  useEffect(() => { if (!processing) return; const t = window.setTimeout(() => setProcessing(false), 2500); return () => clearTimeout(t); }, [processing]);

  // Hands-free loop: after the assistant finishes, listen again.
  const canListen = phase === "on" && !muted && !paused && !halted && !busy && !processing && !review && !interrupted && !voice.speaking && !voice.listening;
  useEffect(() => {
    if (!canListen) return;
    const t = window.setTimeout(() => voiceRef.current?.listen(), 150);
    return () => clearTimeout(t);
  }, [canListen]);

  useEffect(() => () => { stopMeter(); }, [stopMeter]);

  let state: VoiceUiState;
  if (phase === "off") state = "idle";
  else if (phase === "connecting") state = "connecting";
  else if (phase === "ended") state = "ended";
  else if (phase === "error") state = "error";
  else if (voice.speaking) state = "speaking";
  else if (busy) state = "thinking";
  else if (review || processing) state = "processing";
  else if (interrupted) state = "interrupted";
  else if (voice.listening) state = "listening"; // only when the recogniser is really running
  else state = "idle";

  const note = phase === "on" && state === "idle" ? (muted ? "Microphone muted. Unmute to continue." : paused ? "Paused while a care coordinator reviews your request." : halted ? "Emergency guidance was shown. Please follow it. Tap the mic if you want to continue." : null) : null;

  return {
    state, phase, errorKind, muted, review, level, levelAvailable, interim: voice.interim, speaking: voice.speaking, listening: voice.listening,
    startIndex, note, mouth: voice.mouthRef, ttfaMs: voice.lastTtfaMs, supported: voiceSupported(),
    start, end, toggleMute, interrupt, micTap, confirmReview, discardReview, submit,
  };
}
