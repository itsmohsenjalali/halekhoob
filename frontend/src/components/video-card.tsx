"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Download,
  Heart,
  MoreHorizontal,
  Play,
  Volume2,
  VolumeX,
  RefreshCw,
  Headphones,
} from "lucide-react";
import type { Api, Video } from "@/lib/types";
import { duration } from "@/lib/types";
export default function VideoCard({
  video,
  active,
  api,
  update,
  edit,
  download,
  retry,
  observe,
  playAudio,
  audioSelected,
  resumeVideo,
}: {
  video: Video;
  active: boolean;
  api: Api;
  update: (v: Video) => void;
  edit: (v: Video) => void;
  download: (v: Video, kind?: string) => void;
  retry: (v: Video) => void;
  observe: (id: number, el: HTMLElement | null) => void;
  playAudio: (v: Video) => void;
  audioSelected: boolean;
  resumeVideo: (id: number) => void;
}) {
  const media = useRef<HTMLVideoElement>(null);
  const renewed = useRef(false);
  const [muted, setMuted] = useState(true),
    [paused, setPaused] = useState(false),
    [playFailed, setPlayFailed] = useState(false),
    [message, setMessage] = useState("");
  useEffect(() => {
    const el = media.current;
    if (!el) return;
    if (active && !paused) {
      el.play().catch(() => setPlayFailed(true));
    } else el.pause();
  }, [active, paused, video.video_url]);
  useEffect(() => {
    if (!active) setPaused(false);
  }, [active]);
  async function recover() {
    if (renewed.current) {
      setPlayFailed(true);
      setMessage("پخش ممکن نشد؛ دوباره تلاش کن.");
      return;
    }
    renewed.current = true;
    try {
      update(await api<Video>(`videos/${video.id}/`));
    } catch {
      setPlayFailed(true);
    }
  }
  const register = useCallback(
    (el: HTMLElement | null) => observe(video.id, el),
    [observe, video.id],
  );
  return (
    <article ref={register} className="video-card" data-video-id={video.id}>
      <header className="post-header">
        <span className="post-mark">
          {video.platform === "youtube" ? "▶" : "◎"}
        </span>
        <div>
          <strong>{video.title}</strong>
          <span>
            {video.platform === "youtube" ? "یوتیوب" : "اینستاگرام"} · برای یک
            حال بهتر
          </span>
        </div>
        <button
          aria-label={`ویرایش ${video.title}`}
          onClick={() => edit(video)}
        >
          <MoreHorizontal size={23} />
        </button>
      </header>
      {video.status === "ready" && video.video_url ? (
        <div className="video-stage">
          <video
            ref={media}
            src={video.video_url}
            poster={video.thumbnail_url || undefined}
            muted={muted}
            loop
            playsInline
            preload="metadata"
            onError={() => void recover()}
            onPlay={() => setPlayFailed(false)}
          />
          <button
            className="video-touch"
            aria-label={paused || playFailed ? "پخش ویدیو" : "توقف ویدیو"}
            onClick={() => {
              if (!active) {
                resumeVideo(video.id);
                setPaused(false);
                return;
              }
              if (playFailed) {
                media.current
                  ?.play()
                  .catch(() => setMessage("دوباره تلاش کن."));
                setPaused(false);
              } else setPaused(!paused);
            }}
          >
            {(paused || playFailed) && (
              <span className="play-overlay">
                <Play size={32} fill="currentColor" />
              </span>
            )}
          </button>
          <span className="video-duration" dir="ltr">
            {duration(video.duration)}
          </span>
          <button
            className="sound-button"
            aria-label={muted ? "وصل صدای ویدیو" : "قطع صدای ویدیو"}
            onClick={() => setMuted(!muted)}
          >
            {muted ? <VolumeX size={19} /> : <Volume2 size={19} />}
          </button>
        </div>
      ) : (
        <div className="pending-stage">
          <span className="pending-symbol">
            {video.status === "failed" ? "↻" : "◒"}
          </span>
          <strong>
            {video.status === "failed"
              ? "این بار دریافت کامل نشد"
              : video.status === "downloading"
                ? "داریم ویدیوت را آماده می‌کنیم"
                : "ویدیوت در صف دریافت است"}
          </strong>
          <p>
            {video.error ||
              "می‌توانی این صفحه را ببندی؛ دریافت ادامه پیدا می‌کند."}
          </p>
          {video.status === "downloading" && (
            <progress max="100" value={video.progress} />
          )}{" "}
          {video.status === "failed" && (
            <button className="soft-button" onClick={() => retry(video)}>
              <RefreshCw size={16} />
              تلاش دوباره
            </button>
          )}
        </div>
      )}
      <div className="post-actions">
        <button
          className={video.favorite ? "favorited" : ""}
          aria-label={
            video.favorite ? "حذف از علاقه‌مندی‌ها" : "افزودن به علاقه‌مندی‌ها"
          }
          aria-pressed={video.favorite}
          onClick={async () => {
            try {
              const updated = await api<Video>(`videos/${video.id}/`, {
                method: "PATCH",
                body: JSON.stringify({ favorite: !video.favorite }),
              });
              update({
                ...updated,
                video_url: video.video_url,
                audio_url: video.audio_url,
                thumbnail_url: video.thumbnail_url,
              });
            } catch (e) {
              setMessage((e as Error).message);
            }
          }}
        >
          <Heart size={23} fill={video.favorite ? "currentColor" : "none"} />
        </button>
        <button
          aria-label="دانلود ویدیو"
          disabled={video.status !== "ready"}
          onClick={() => download(video)}
        >
          <Download size={22} />
        </button>
        {video.status === "ready" && video.audio_url && (
          <button
            className="post-audio"
            aria-label={audioSelected ? "بستن صدای این ویدیو" : "پخش صوتی این ویدیو"}
            aria-pressed={audioSelected}
            onClick={() => playAudio(video)}
          >
            <Headphones size={19} />
            <span>{audioSelected ? "در پخش‌کننده" : "فقط صدا"}</span>
          </button>
        )}
        <div className="post-tags">
          {video.categories.map((c) => (
            <span key={c.id}>
              {c.symbol} {c.name}
            </span>
          ))}
        </div>
      </div>
      {video.note && <p className="post-note">{video.note}</p>}
      {message && (
        <p className="inline-error" role="status">
          {message}
        </p>
      )}
    </article>
  );
}
