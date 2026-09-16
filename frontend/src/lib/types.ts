export type Category = { id: number; name: string; symbol: string };
export type Video = {
  id: number;
  title: string;
  note: string;
  source_url: string;
  platform: string;
  status: string;
  progress: number;
  error: string;
  error_code: string;
  favorite: boolean;
  duration: number;
  size_bytes: number;
  categories: Category[];
  video_url: string | null;
  audio_url: string | null;
  thumbnail_url: string | null;
  created_at: string;
};
export type Profile = {
  name: string;
  email: string;
  storage_used: number;
  storage_reserved: number;
  storage_limit: number;
  daily_used: number;
  daily_limit: number;
  queue_limit: number;
};
export type Api = <T>(path: string, options?: RequestInit) => Promise<T>;
export function bytes(n: number) {
  return n >= 1e9
    ? `${(n / 1e9).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} گیگابایت`
    : `${(n / 1e6).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} مگابایت`;
}
export function duration(n: number) {
  return `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, "0")}`;
}
