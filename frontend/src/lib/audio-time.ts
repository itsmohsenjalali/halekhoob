/** Parse m:ss or h:mm:ss, including Persian/Arabic numerals. */
export function parseAudioTime(input: string, length: number): number | null {
  const ascii = input.trim().replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 0x6f0))
    .replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 0x660));
  if (!/^\d+:[0-5]\d(?::[0-5]\d)?$/.test(ascii)) return null;
  const seconds = ascii.split(":").map(Number).reduce((total, part) => total * 60 + part, 0);
  return Number.isFinite(length) && Number.isSafeInteger(seconds) && seconds <= length ? seconds : null;
}
