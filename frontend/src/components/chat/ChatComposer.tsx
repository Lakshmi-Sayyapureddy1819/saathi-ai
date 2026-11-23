import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Mic, MicOff, SendHorizontal } from "lucide-react";
import { useDictation, type VoiceLang } from "../../voice";
import { IconButton } from "../ui";

interface Props { onListening?: (on: boolean) => void; busy: boolean; paused: boolean; maxChars: number; onSend: (text: string) => void; lang?: VoiceLang }

/** Enter sends, Shift+Enter adds a line, "/" focuses from anywhere, Esc clears. */
export function ChatComposer({ onListening, busy, paused, maxChars, onSend, lang = "en-IN" }: Props) {
  const [draft, setDraft] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const base = useRef("");
  const dict = useDictation((text) => setDraft(base.current ? `${base.current} ${text}` : text), lang);

  useEffect(() => { onListening?.(dict.listening); }, [dict.listening, onListening]);

  useEffect(() => {
    const el = ref.current; if (!el) return;
    el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  useEffect(() => {
    const k = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) && !t.isContentEditable) { e.preventDefault(); ref.current?.focus(); }
    };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, []);

  const text = draft.trim();
  const tooLong = text.length > maxChars;
  const canSend = !!text && !busy && !paused && !tooLong;
  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!canSend) return;
    if (dict.listening) dict.stop();
    onSend(text); setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
    else if (e.key === "Escape") setDraft("");
  };
  const toggleDictation = () => { if (dict.listening) { dict.stop(); return; } base.current = draft.trim(); dict.start(); };

  return (
    <form className="composer" onSubmit={submit} aria-label="Message composer">
      <div className={`composer-box${paused ? " disabled" : ""}`}>
        <label htmlFor="msg" className="sr-only">Message Mimi</label>
        <textarea id="msg" ref={ref} rows={1} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} disabled={paused}
          placeholder={paused ? "Waiting for a care coordinator…" : "Message Mimi… (English, Hindi or Hinglish)"}
          aria-invalid={tooLong} aria-describedby="msg-help" autoComplete="off" />
        <div className="composer-actions">
          {dict.supported && (
            <IconButton icon={dict.listening ? MicOff : Mic} label={dict.listening ? "Stop dictation" : "Dictate message"} on={dict.listening}
              onClick={toggleDictation} disabled={paused} data-testid="dictate" />
          )}
          <button type="submit" className="send-btn" disabled={!canSend} aria-label="Send"><SendHorizontal size={19} aria-hidden="true" /></button>
        </div>
      </div>
      <div className="composer-foot" id="msg-help">
        {tooLong ? <span className="help err" role="alert">Too long: {text.length}/{maxChars} characters. Please shorten it.</span>
          : dict.error ? <span className="help err" role="alert">{dict.error}</span>
            : <span className="help">Enter to send · Shift+Enter for a new line · press / to focus{text.length > maxChars * 0.8 ? ` · ${text.length}/${maxChars}` : ""}</span>}
        <span className="help">Saathi is an AI assistant, not a doctor. In an emergency call 112.</span>
      </div>
    </form>
  );
}
