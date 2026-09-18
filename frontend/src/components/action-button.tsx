"use client";
import { useRef, useState, type ButtonHTMLAttributes } from "react";
import { LoaderCircle } from "lucide-react";

export default function ActionButton({ onAction, children, disabled, ...props }: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> & { onAction: () => Promise<unknown> }) {
  const locked = useRef(false);
  const [busy, setBusy] = useState(false);
  return <button {...props} type={props.type || "button"} disabled={disabled || busy} aria-busy={busy} onClick={async () => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    try { await onAction(); } finally { locked.current = false; setBusy(false); }
  }}>{busy && <LoaderCircle className="spin" size={18} aria-hidden="true" />}{children}</button>;
}
