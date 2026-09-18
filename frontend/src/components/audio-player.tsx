"use client";
import { useEffect, useRef, useState } from "react";
import {
  Pause,
  Play,
  SkipBack,
  SkipForward,
  X,
  Volume2,
  VolumeX,
  Repeat,
  Repeat1,
  LoaderCircle,
} from "lucide-react";
import type { Api, Video } from "@/lib/types";
import { nextAudioIndex, type RepeatMode } from "@/lib/audio-repeat";
import { duration } from "@/lib/types";
export default function AudioPlayer({
  tracks,
  api,
  onClose,
}: {
  tracks: Video[];
  api: Api;
  onClose: () => void;
}) {
  const audio = useRef<HTMLAudioElement>(null),
    renewed = useRef(false);
  const [index, setIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [position, setPosition] = useState(0),
    [length, setLength] = useState(0),
    [muted, setMuted] = useState(false),
    [error, setError] = useState(""),
    [buffering, setBuffering] = useState(true),
    [repeat, setRepeat] = useState<RepeatMode>("off");
  const track = tracks[index];
  const current = useRef({ index, tracks });
  current.current = { index, tracks };
  useEffect(() => {
    setIndex(0);
  }, [tracks]);
  useEffect(() => {
    const el = audio.current;
    if (!el || !track) return;
    renewed.current = false;
    setError("");
    setPosition(0);
    setLength(0);
    setBuffering(true);
    el.src = track.audio_url || "";
    el.play().catch(() => { setBuffering(false); setError("برای شروع پخش، دکمهٔ پخش را بزن."); });
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        artist: "حال‌خوب",
        artwork: track.thumbnail_url
          ? [{ src: new URL(track.thumbnail_url, location.origin).href }]
          : [],
      });
    }
    try {
      const nav = navigator as Navigator & { audioSession?: { type: string } };
      if (nav.audioSession) nav.audioSession.type = "playback";
    } catch {}
  }, [track]);
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    const actions: Record<string, MediaSessionActionHandler> = {
      play: () => {
        audio.current
          ?.play()
          .catch(() => setError("پخش ممکن نشد؛ دوباره تلاش کن."));
      },
      pause: () => audio.current?.pause(),
      previoustrack: () => setIndex((i) => Math.max(0, i - 1)),
      nexttrack: () =>
        setIndex((i) => Math.min(current.current.tracks.length - 1, i + 1)),
      seekto: (d) => {
        if (audio.current && d.seekTime !== undefined)
          audio.current.currentTime = d.seekTime;
      },
      seekbackward: (d) => {
        if (audio.current)
          audio.current.currentTime = Math.max(
            0,
            audio.current.currentTime - (d.seekOffset || 10),
          );
      },
      seekforward: (d) => {
        if (audio.current)
          audio.current.currentTime = Math.min(
            audio.current.duration,
            audio.current.currentTime + (d.seekOffset || 10),
          );
      },
    };
    for (const [name, fn] of Object.entries(actions)) {
      try {
        navigator.mediaSession.setActionHandler(name as MediaSessionAction, fn);
      } catch {}
    }
    return () => {
      for (const name of Object.keys(actions)) {
        try {
          navigator.mediaSession.setActionHandler(
            name as MediaSessionAction,
            null,
          );
        } catch {}
      }
      navigator.mediaSession.metadata = null;
    };
  }, []);
  useEffect(() => {
    if ("mediaSession" in navigator)
      navigator.mediaSession.playbackState = playing ? "playing" : "paused";
  }, [playing]);
  async function recover() {
    if (renewed.current) {
      setBuffering(false);
      setError("فایل در دسترس نیست؛ دوباره تلاش کن یا به بعدی برو.");
      return;
    }
    renewed.current = true;
    const el = audio.current;
    if (!el || !track) return;
    const time = el.currentTime;
    const expectedId = track.id;
    setBuffering(true);
    try {
      const updated = await api<Video>(`videos/${track.id}/`);
      if (current.current.tracks[current.current.index]?.id !== expectedId) return;
      if (!updated.audio_url) throw Error();
      el.src = updated.audio_url;
      el.addEventListener(
        "loadedmetadata",
        () => {
          if (current.current.tracks[current.current.index]?.id !== expectedId) return;
          el.currentTime = time;
          el.play().catch(() => setError("برای ادامه پخش را بزن."));
        },
        { once: true },
      );
      el.load();
    } catch {
      setBuffering(false);
      setError("ارتباط برقرار نشد؛ دوباره تلاش کن.");
    }
  }
  return (
    <section className="audio-dock" aria-label={tracks.length === 1 ? "پخش صوتی ویدیو" : "پخش صوتی پیوسته"}>
      <audio
        ref={audio}
        muted={muted}
        loop={repeat === "one" || (repeat === "all" && tracks.length === 1)}
        onWaiting={() => setBuffering(true)}
        onPlaying={() => setBuffering(false)}
        onCanPlay={() => setBuffering(false)}
        onPlay={() => {
          setPlaying(true);
          setError("");
        }}
        onPause={() => setPlaying(false)}
        onTimeUpdate={() => setPosition(audio.current?.currentTime || 0)}
        onLoadedMetadata={() => setLength(audio.current?.duration || 0)}
        onEnded={() => {
          const next = nextAudioIndex(index, tracks.length, repeat);
          if (next === null) setPlaying(false);
          else if (next === index && audio.current) {
            audio.current.currentTime = 0;
            void audio.current.play().catch(() => setError("برای ادامه پخش را بزن."));
          } else setIndex(next);
        }}
        onError={() => void recover()}
      />
      <div className="audio-title">
        <span className="eyebrow">
          {tracks.length === 1 ? "فقط صدای این ویدیو" : `پخش پیوسته · ${(index + 1).toLocaleString("fa-IR")} از ${tracks.length.toLocaleString("fa-IR")}`}
        </span>
        <strong>{track?.title}</strong>
        {error && <small role="status">{error}</small>}
      </div>
      <div className="audio-controls" dir="ltr">
        {tracks.length > 1 && <button
          aria-label="صدای قبلی"
          disabled={index === 0}
          onClick={() => setIndex(index - 1)}
        >
          <SkipBack size={18} />
        </button>}
        <button
          className="round-play"
          aria-busy={buffering}
          disabled={buffering && !playing}
          aria-label={playing ? "توقف صدا" : "پخش صدا"}
          onClick={() => {
            if (error) {
              renewed.current = false;
              void recover();
            } else if (audio.current?.paused)
              audio.current
                .play()
                .catch(() => setError("برای ادامه دوباره تلاش کن."));
            else audio.current?.pause();
          }}
        >
          {buffering ? <LoaderCircle className="spin" size={20} /> : playing ? <Pause size={20} /> : <Play size={20} />}
        </button>
        {tracks.length > 1 && <button
          aria-label="صدای بعدی"
          disabled={index === tracks.length - 1}
          onClick={() => setIndex(index + 1)}
        >
          <SkipForward size={18} />
        </button>}
      </div>
      <div className="audio-seek" dir="ltr">
        <small>{duration(position)}</small>
        <input
          aria-label="زمان پخش صدا"
          type="range"
          min="0"
          max={Number.isFinite(length) ? length : 0}
          value={Math.min(position, length || 0)}
          step="0.1"
          onChange={(e) => {
            if (audio.current)
              audio.current.currentTime = Number(e.target.value);
          }}
        />
        <small>{duration(length || 0)}</small>
      </div>
      <button className="audio-repeat" aria-pressed={repeat !== "off"} aria-label={repeat === "off" ? "تکرار خاموش" : repeat === "one" ? "تکرار همین کلیپ" : "تکرار کل فهرست"} title="تغییر حالت تکرار" onClick={() => setRepeat(value => tracks.length === 1 ? (value === "off" ? "one" : "off") : value === "off" ? "all" : value === "all" ? "one" : "off")}>
        {repeat === "one" ? <Repeat1 size={20} /> : <Repeat size={20} />}
        <span>{repeat === "off" ? "تکرار خاموش" : repeat === "one" ? "همین کلیپ" : "کل فهرست"}</span>
      </button>
      <button
        className="audio-mute"
        aria-label={muted ? "وصل صدا" : "قطع صدا"}
        onClick={() => setMuted(!muted)}
      >
        {muted ? <VolumeX size={19} /> : <Volume2 size={19} />}
      </button>
      <button
        className="audio-close"
        aria-label="بستن پخش صوتی"
        onClick={() => {
          audio.current?.pause();
          onClose();
        }}
      >
        <X size={19} />
      </button>
    </section>
  );
}
