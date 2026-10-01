"use client";
import { useRef, useState } from "react";
import { duration } from "@/lib/types";

export default function AudioSeek({ position, length, onSeek }: {
  position: number;
  length: number;
  onSeek: (seconds: number) => void;
}) {
  const [draft, setDraft] = useState<number | null>(null);
  const dragging = useRef(false);
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
      <small>{duration(shown)}</small>
      <small>{duration(maximum)}</small>
    </div>
  </div>;
}
