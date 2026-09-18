export type RepeatMode = "off" | "all" | "one";

export function nextAudioIndex(index: number, count: number, repeat: RepeatMode): number | null {
  if (count <= 0) return null;
  if (repeat === "one") return index;
  if (index < count - 1) return index + 1;
  return repeat === "all" ? 0 : null;
}
