"use client";
import { useRef, useState } from "react";
import { Pencil, X } from "lucide-react";
import { duration } from "@/lib/types";
import { parseAudioTime } from "@/lib/audio-time";

export default function AudioSeek({ position, length, onSeek }: {
  position: number;
  length: number;
  onSeek: (seconds: number) => void;
}) {
  const [draft, setDraft] = useState<number | null>(null);
  const dragging = useRef(false);
  const [editing, setEditing] = useState(false);
  const [time, setTime] = useState("");
  const [error, setError] = useState("");
  const maximum = Number.isFinite(length) && length > 0 ? length : 0;
  const shown = Math.max(0, Math.min(Math.floor(draft ?? position), maximum));
  function cancelDrag() {
    dragging.current = false;
    setDraft(null);
  }
  return <div className="audio-seek" dir="ltr">
    <input
      className="audio-timeline"
      aria-label="زمان پخش صدا"
      aria-valuetext={duration(shown)}
      type="range"
      min="0"
      max={maximum}
      value={shown}
      step="1"
      disabled={!maximum}
      onPointerDown={e => {
        if (e.button !== 0 || !maximum) return;
        dragging.current = true;
        setDraft(Number(e.currentTarget.value));
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onChange={e => {
        const next = Number(e.currentTarget.value);
        if (dragging.current) setDraft(next);
        else onSeek(next); // Keyboard and assistive controls seek immediately.
      }}
      onPointerUp={e => {
        if (!dragging.current) return;
        const next = Number(e.currentTarget.value);
        dragging.current = false;
        onSeek(next);
        setDraft(null);
      }}
      onPointerCancel={cancelDrag}
      onLostPointerCapture={() => { if (dragging.current) cancelDrag(); }}
      onBlur={() => { if (dragging.current) cancelDrag(); }}
    />
    <div className="audio-times">
      {editing ? <form className="audio-exact-time" onSubmit={e => {
        e.preventDefault();
        const seconds = parseAudioTime(time, maximum);
        if (seconds === null) {
          setError(`زمانی بین 0:00 و ${duration(maximum)} بنویس؛ مثلاً 11:20.`);
          return;
        }
        onSeek(seconds);
        setEditing(false);
        setError("");
      }}>
        <input autoFocus aria-label="زمان دقیق (دقیقه:ثانیه)" type="text" dir="ltr"
          value={time} placeholder="11:20" maxLength={12} autoComplete="off" spellCheck={false}
          aria-invalid={!!error} onFocus={e => e.currentTarget.select()}
          onChange={e => { setTime(e.target.value); setError(""); }}
          onKeyDown={e => { if (e.key === "Escape") { setEditing(false); setError(""); } }} />
        <button type="submit">برو</button>
        <button type="button" aria-label="انصراف از تغییر زمان" onClick={() => { setEditing(false); setError(""); }}><X size={14} /></button>
      </form> : <button className="audio-time-edit" type="button" disabled={!maximum}
        aria-label={`رفتن به زمان دقیق؛ زمان فعلی ${duration(shown)}`}
        title="برای واردکردن زمان دقیق بزن"
        onClick={() => { setTime(duration(shown)); setEditing(true); }}>
        <span>{duration(shown)}</span><Pencil size={12} /><span className="audio-time-hint" dir="rtl">زمان دلخواه</span>
      </button>}
      <small>{duration(maximum)}</small>
    </div>
    {error && <small className="audio-time-error" role="alert" dir="rtl">{error}</small>}
  </div>;
}
