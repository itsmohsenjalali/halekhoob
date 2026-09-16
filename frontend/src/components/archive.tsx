"use client";
import { useAuth, UserButton } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Plus,
  Search,
  Headphones,
  Heart,
  Home,
  Folder,
  Clock,
  Leaf,
  Download,
  X,
  ArrowDown,
  Trash2,
  Check,
  LoaderCircle,
} from "lucide-react";
import type { Api, Category, Profile, Video } from "@/lib/types";
import { bytes } from "@/lib/types";
import VideoCard from "./video-card";
import AudioPlayer from "./audio-player";

type DialogState = "add" | "categories" | Video | null;
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="modal"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button aria-label="بستن" onClick={onClose}>
          <X size={21} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export default function Archive() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null),
    [categories, setCategories] = useState<Category[]>([]),
    [items, setItems] = useState<Video[]>([]),
    [next, setNext] = useState<number | null>(null);
  const [category, setCategory] = useState<number | null>(null),
    [mode, setMode] = useState(""),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true),
    [loadingMore, setLoadingMore] = useState(false),
    [notice, setNotice] = useState(""),
    [modal, setModal] = useState<DialogState>(null),
    [tracks, setTracks] = useState<Video[]>([]),
    [active, setActive] = useState<number | null>(null),
    [hidden, setHidden] = useState(false);
  const nodes = useRef(new Map<number, HTMLElement>()),
    ratios = useRef(new Map<number, number>()),
    observer = useRef<IntersectionObserver | null>(null),
    sentinel = useRef<HTMLDivElement>(null),
    feed = useRef<HTMLElement>(null);
  const api: Api = useCallback(
    async <T,>(path: string, options: RequestInit = {}) => {
      let token = await getToken();
      if (!token) throw new Error("برای ادامه دوباره با گوگل وارد شو.");
      const send = () =>
        fetch("/api/v1/" + path, {
          ...options,
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            ...options.headers,
            Authorization: "Bearer " + token,
          },
        });
      let response = await send();
      if (response.status === 401) {
        token = await getToken({ skipCache: true });
        response = await send();
      }
      const data = await response
        .json()
        .catch(() => ({ error: { message: "ارتباط با سرور برقرار نشد." } }));
      if (!response.ok)
        throw new Error(
          data.error?.message || "عملیات انجام نشد؛ دوباره تلاش کن.",
        );
      return data as T;
    },
    [getToken],
  );
  const params = new URLSearchParams();
  if (category) params.set("category", String(category));
  if (mode) params.set("filter", mode);
  if (query) params.set("q", query);
  const filters = params.toString();
  const currentFilters = useRef(filters);
  currentFilters.current = filters;
  const refreshProfile = useCallback(async () => {
    setProfile(await api<Profile>("me/"));
  }, [api]);
  const refreshCategories = useCallback(async () => {
    setCategories((await api<{ items: Category[] }>("categories/")).items);
  }, [api]);
  useEffect(() => {
    const id = setTimeout(() => setQuery(search), 300);
    return () => clearTimeout(id);
  }, [search]);
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    Promise.all([refreshProfile(), refreshCategories()]).catch((e) =>
      setNotice(e.message),
    );
  }, [isLoaded, isSignedIn, refreshProfile, refreshCategories]);
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    const controller = new AbortController();
    setLoading(true);
    setActive(null);
    api<{ items: Video[]; next_page: number | null }>(`videos/?${filters}`, {
      signal: controller.signal,
    })
      .then((data) => {
        setItems(data.items);
        setNext(data.next_page);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setNotice(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, filters, isLoaded, isSignedIn]);
  useEffect(() => {
    if (mode !== "pending" || !isSignedIn) return;
    const id = setInterval(() => {
      if (document.hidden) return;
      api<{ items: Video[]; next_page: number | null }>(`videos/?${filters}`)
        .then((data) => {
          setItems(data.items);
          setNext(data.next_page);
          void refreshProfile();
        })
        .catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [mode, isSignedIn, api, filters, refreshProfile]);
  useEffect(() => {
    const changed = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);
  useEffect(() => {
    observer.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          ratios.current.set(
            Number((entry.target as HTMLElement).dataset.videoId),
            entry.isIntersecting ? entry.intersectionRatio : 0,
          );
        const visible = [...ratios.current.entries()].sort(
          (a, b) => b[1] - a[1],
        );
        setActive(visible[0]?.[1] > 0.25 ? visible[0][0] : null);
      },
      {
        threshold: [0, 0.25, 0.5, 0.65, 0.8, 1],
        rootMargin: "-85px 0px -40px 0px",
      },
    );
    nodes.current.forEach((el) => observer.current?.observe(el));
    return () => observer.current?.disconnect();
  }, []);
  const observe = useCallback((id: number, el: HTMLElement | null) => {
    const old = nodes.current.get(id);
    if (old) observer.current?.unobserve(old);
    if (el) {
      nodes.current.set(id, el);
      observer.current?.observe(el);
    } else {
      nodes.current.delete(id);
      ratios.current.delete(id);
    }
  }, []);
  const loadMore = useCallback(async () => {
    if (!next || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await api<{ items: Video[]; next_page: number | null }>(
        `videos/?${filters}&page=${next}`,
      );
      if (currentFilters.current !== filters) return;
      setItems((previous) => [
        ...previous,
        ...data.items.filter((v) => !previous.some((p) => p.id === v.id)),
      ]);
      setNext(data.next_page);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }, [api, filters, next, loadingMore]);
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !next) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) void loadMore();
      },
      { rootMargin: "400px" },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [next, loadMore]);
  function update(video: Video) {
    setItems((old) => old.map((v) => (v.id === video.id ? video : v)));
  }
  function chooseMode(value: string) {
    setMode(value);
    feed.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  async function download(video: Video, kind = "video") {
    try {
      const data = await api<{ url: string }>(
        `videos/${video.id}/download/?kind=${kind}`,
      );
      const anchor = document.createElement("a");
      anchor.href = data.url;
      anchor.rel = "noopener noreferrer";
      anchor.target = "_blank";
      anchor.download = "";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setNotice("لینک دانلود باز شد؛ فایل را در بخش دانلودهای مرورگر پیدا می‌کنی.");
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function retry(video: Video) {
    try {
      update(await api<Video>(`videos/${video.id}/retry/`, { method: "POST" }));
      void refreshProfile();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function launchAudio() {
    try {
      const data = await api<{ tracks: Video[] }>(`playlist/?${filters}`);
      if (!data.tracks.length) {
        setNotice("در این انتخاب، ویدیوی آمادهٔ دارای صدا نیست.");
        return;
      }
      setTracks(data.tracks);
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  const selected = categories.find((c) => c.id === category);
  if (!isLoaded)
    return (
      <main className="boot">
        <Leaf size={36} />
        <p>داریم حال‌خوب را آماده می‌کنیم…</p>
      </main>
    );
  if (!isSignedIn)
    return (
      <main className="auth-page">
        <h1>به حال‌خوب خوش آمدی</h1>
        <a className="primary-button" href="/sign-in">
          ورود با گوگل
        </a>
      </main>
    );
  return (
    <div className={tracks.length ? "app has-audio" : "app"}>
      <header className="mobile-header">
        <a className="brand" href="/">
          حال‌خوب <Leaf size={23} />
        </a>
        <UserButton />
      </header>
      <div className="shell">
        <aside className="sidebar">
          <a className="brand" href="/">
            حال‌خوب <Leaf size={29} />
            <span>لحظه‌های خوبت را نگه دار.</span>
          </a>
          <nav aria-label="منوی اصلی">
            <button
              className={!mode ? "selected" : ""}
              onClick={() => chooseMode("")}
            >
              <Home />
              خانه
            </button>
            <button
              className={mode === "favorites" ? "selected" : ""}
              onClick={() => chooseMode("favorites")}
            >
              <Heart />
              دوست‌داشتنی‌ها
            </button>
            <button
              className={mode === "pending" ? "selected" : ""}
              onClick={() => chooseMode("pending")}
            >
              <Clock />
              صف دریافت
            </button>
            <button onClick={() => setModal("categories")}>
              <Folder />
              دسته‌های من
            </button>
          </nav>
          <button className="primary-button" onClick={() => setModal("add")}>
            <Plus size={20} />
            ذخیرهٔ ویدیوی تازه
          </button>
          <div className="sidebar-bottom">
            <span className="eyebrow">آرشیو شخصی تو</span>
            <p>
              گاهی یک ویدیو،
              <br />
              همان چیزی‌ست که نیاز داریم.
            </p>
            <div className="user">
              <UserButton />
              <span>
                {profile?.name || "حساب من"}
                <small>ورود با گوگل</small>
              </span>
            </div>
          </div>
        </aside>
        <main className="feed" ref={feed}>
          <header className="feed-header">
            <div>
              <span className="eyebrow">یک مکث برای خودت</span>
              <h1>
                {mode === "pending"
                  ? "در راه آرشیوت"
                  : mode === "favorites"
                    ? "دوست‌داشتنی‌های تو"
                    : "امروز چه حسی می‌خواهی؟"}
              </h1>
            </div>
            <button
              className="add-mobile"
              aria-label="ذخیرهٔ ویدیوی تازه"
              onClick={() => setModal("add")}
            >
              <Plus />
            </button>
          </header>
          <div className="filter-panel">
            <div className="mood-strip" aria-label="فیلتر دسته">
              <button
                className={!category ? "active" : ""}
                onClick={() => setCategory(null)}
              >
                همهٔ حس‌ها
              </button>
              {categories.map((c) => (
                <button
                  key={c.id}
                  className={category === c.id ? "active" : ""}
                  onClick={() => setCategory(c.id)}
                >
                  <span>{c.symbol}</span>
                  {c.name}
                </button>
              ))}
            </div>
            <div className="feed-tools">
              <label className="search">
                <Search size={18} />
                <input
                  aria-label="جست‌وجوی آرشیو"
                  placeholder="بین لحظه‌های خوبت بگرد…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <button
                className="listen-button"
                onClick={() => void launchAudio()}
              >
                <Headphones size={18} />
                <span>پخش صوتی</span>
              </button>
            </div>
          </div>
          <div className="feed-label">
            <span>
              {selected
                ? selected.name
                : mode === "favorites"
                  ? "ویدیوهای محبوب تو"
                  : mode === "pending"
                    ? "وضعیت دریافت‌ها"
                    : "برای حالِ خوبِ تو"}
            </span>
            <span>آرشیو خصوصی</span>
          </div>
          {loading ? (
            <div className="empty">
              <LoaderCircle className="spin" />
              <p>در حال دریافت آرشیو…</p>
            </div>
          ) : items.length ? (
            items.map((v) => (
              <VideoCard
                key={v.id}
                video={v}
                active={active === v.id && !hidden && !tracks.length}
                api={api}
                update={update}
                edit={setModal}
                download={download}
                retry={retry}
                observe={observe}
              />
            ))
          ) : (
            <section className="empty">
              <Leaf size={44} />
              <h2>
                {query || category
                  ? "هنوز ویدیویی در این انتخاب نیست"
                  : "جای لحظه‌های خوبت اینجاست"}
              </h2>
              <p>
                {mode === "pending"
                  ? "همه‌چیز آماده است؛ دریافتی در انتظار نیست."
                  : "یک لینک ذخیره کن تا هر وقت خواستی، دوباره به آن برگردی."}
              </p>
              <button
                className="primary-button"
                onClick={() => setModal("add")}
              >
                <Plus size={18} />
                اولین ویدیو را اضافه کن
              </button>
            </section>
          )}
          <div ref={sentinel} className="load-more">
            {next && (
              <button disabled={loadingMore} onClick={() => void loadMore()}>
                {loadingMore ? "در حال دریافت…" : "ویدیوهای بیشتر"}
                <ArrowDown size={15} />
              </button>
            )}
          </div>
        </main>
        <aside className="right-rail">
          <div className="welcome">
            <span className="eyebrow">به وقتِ خودت</span>
            <h2>
              کمی آرام‌تر،
              <br />
              کمی امیدوارتر.
            </h2>
            <p>اینجا برای ویدیوهایی‌ست که دوست داری دوباره و دوباره ببینی.</p>
            <Leaf size={47} strokeWidth={1} />
          </div>
          <section className="storage">
            <div className="section-title">
              <strong>فضای آرشیو</strong>
              <Folder size={18} />
            </div>
            <progress
              aria-label="مصرف فضای آرشیو"
              value={
                profile ? profile.storage_used + profile.storage_reserved : 0
              }
              max={profile?.storage_limit || 1}
            />
            <p>
              {bytes(profile?.storage_used || 0)} از{" "}
              {bytes(profile?.storage_limit || 0)}
            </p>
            {!!profile?.storage_reserved && (
              <small>
                {bytes(profile.storage_reserved)} برای دریافت‌ها رزرو شده
              </small>
            )}
            <small>
              دریافت امروز: {profile?.daily_used.toLocaleString("fa-IR") || "۰"}{" "}
              از {profile?.daily_limit.toLocaleString("fa-IR") || "۵"}
            </small>
          </section>
          <p className="rail-foot">
            برای خودت نگه دار.
            <br />
            برای حالِ خوبِ روزهای بعد.
          </p>
        </aside>
      </div>
      <nav className="mobile-nav" aria-label="منوی موبایل">
        <button
          aria-label="خانه"
          className={!mode ? "selected" : ""}
          onClick={() => chooseMode("")}
        >
          <Home size={22} />
        </button>
        <button
          aria-label="علاقه‌مندی‌ها"
          className={mode === "favorites" ? "selected" : ""}
          onClick={() => chooseMode("favorites")}
        >
          <Heart size={22} />
        </button>
        <button
          className="nav-add"
          aria-label="افزودن ویدیو"
          onClick={() => setModal("add")}
        >
          <Plus size={26} />
        </button>
        <button
          aria-label="صف دریافت"
          className={mode === "pending" ? "selected" : ""}
          onClick={() => chooseMode("pending")}
        >
          <Clock size={22} />
        </button>
        <button aria-label="دسته‌های من" onClick={() => setModal("categories")}>
          <Folder size={22} />
        </button>
      </nav>
      {notice && (
        <div className="toast" role="status">
          <span>{notice}</span>
          <button aria-label="بستن پیام" onClick={() => setNotice("")}>
            <X size={18} />
          </button>
        </div>
      )}
      {tracks.length > 0 && (
        <AudioPlayer tracks={tracks} api={api} onClose={() => setTracks([])} />
      )}
      {modal === "categories" && (
        <Modal title="دسته‌های من" onClose={() => setModal(null)}>
          <CategoryManager
            categories={categories}
            api={api}
            refresh={refreshCategories}
            onDeleted={(id) => {
              if (category === id) setCategory(null);
              setItems((old) =>
                old.map((v) => ({
                  ...v,
                  categories: v.categories.filter((c) => c.id !== id),
                })),
              );
            }}
          />
        </Modal>
      )}
      {modal && modal !== "categories" && (
        <Modal
          title={modal === "add" ? "یک لحظهٔ خوب ذخیره کن" : "ویرایش ویدیو"}
          onClose={() => setModal(null)}
        >
          <VideoForm
            video={modal === "add" ? undefined : modal}
            categories={categories}
            api={api}
            initialCategory={category}
            onSaved={(video) => {
              if (modal === "add") {
                setMode(video.status === "ready" ? "" : "pending");
                setCategory(null);
                setSearch("");
                setQuery("");
                setItems((old) => [
                  video,
                  ...old.filter((v) => v.id !== video.id),
                ]);
                setNotice(
                  video.status === "ready"
                    ? "این ویدیو از قبل در آرشیوت هست."
                    : "ویدیو ثبت شد؛ دریافت در پس‌زمینه ادامه پیدا می‌کند.",
                );
              } else update(video);
              setModal(null);
              void refreshProfile();
            }}
            onDelete={(video) => {
              setItems((old) => old.filter((v) => v.id !== video.id));
              setTracks((old) => old.filter((v) => v.id !== video.id));
              setModal(null);
              void refreshProfile();
            }}
            onDownload={download}
          />
        </Modal>
      )}
    </div>
  );
}
function CategoryManager({
  categories,
  api,
  refresh,
  onDeleted,
}: {
  categories: Category[];
  api: Api;
  refresh: () => Promise<void>;
  onDeleted: (id: number) => void;
}) {
  const [name, setName] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  async function action(path: string, method: string, data?: object) {
    setBusy(true);
    setMessage("");
    try {
      await api(path, {
        method,
        body: data ? JSON.stringify(data) : undefined,
      });
      await refresh();
      return true;
    } catch (e) {
      setMessage((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="category-manager">
      <p className="muted">این دسته‌ها فقط متعلق به حساب تو هستند.</p>
      <form
        className="category-create"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await action("categories/", "POST", { name })) setName("");
        }}
      >
        <input
          aria-label="نام دستهٔ جدید"
          placeholder="مثلاً تمرکز"
          value={name}
          maxLength={40}
          required
          onChange={(e) => setName(e.target.value)}
        />
        <button className="primary-button" disabled={busy}>
          <Plus size={18} />
          ساخت دسته
        </button>
      </form>
      <div className="category-list">
        {categories.map((c) => (
          <form
            key={c.id}
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              await action(`categories/${c.id}/`, "PATCH", {
                name: data.get("name"),
              });
            }}
          >
            <span>{c.symbol}</span>
            <input
              aria-label={`نام دسته ${c.name}`}
              name="name"
              defaultValue={c.name}
              maxLength={40}
              required
            />
            <button disabled={busy} aria-label={`ذخیرهٔ دسته ${c.name}`}>
              <Check size={18} />
            </button>
            <button
              disabled={busy}
              type="button"
              aria-label={`حذف دسته ${c.name}`}
              onClick={async () => {
                if (
                  confirm(
                    "دسته حذف شود؟ ویدیوهای آن در آرشیو باقی می‌مانند.",
                  ) &&
                  (await action(`categories/${c.id}/`, "DELETE"))
                )
                  onDeleted(c.id);
              }}
            >
              <Trash2 size={18} />
            </button>
          </form>
        ))}
      </div>
      {message && (
        <p className="inline-error" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
function VideoForm({
  video,
  categories,
  api,
  initialCategory,
  onSaved,
  onDelete,
  onDownload,
}: {
  video?: Video;
  categories: Category[];
  api: Api;
  initialCategory: number | null;
  onSaved: (v: Video) => void;
  onDelete: (v: Video) => void;
  onDownload: (v: Video, kind?: string) => void;
}) {
  const [ids, setIds] = useState<number[]>(
      video
        ? video.categories.map((c) => c.id)
        : initialCategory
          ? [initialCategory]
          : categories[0]
            ? [categories[0].id]
            : [],
    ),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    const form = new FormData(e.currentTarget);
    const data = {
      source_url: form.get("source_url"),
      title: form.get("title"),
      note: form.get("note"),
      category_ids: ids,
    };
    try {
      if (video)
        onSaved(
          await api<Video>(`videos/${video.id}/`, {
            method: "PATCH",
            body: JSON.stringify(data),
          }),
        );
      else {
        const result = await api<{ video: Video; duplicate: boolean }>(
          "videos/",
          { method: "POST", body: JSON.stringify(data) },
        );
        onSaved(result.video);
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="video-form" onSubmit={submit}>
      {!video && (
        <label>
          لینک ویدیو
          <input
            name="source_url"
            type="url"
            dir="ltr"
            placeholder="https://www.instagram.com/reel/…"
            required
            maxLength={1000}
          />
          <small>
            لینک عمومی یوتیوب یا اینستاگرام؛ تا ۲۰ دقیقه و ۵۰۰ مگابایت
          </small>
        </label>
      )}
      <label>
        عنوان دلخواه
        <input
          name="title"
          placeholder="نامی که یادت می‌ماند"
          defaultValue={video?.title || ""}
          maxLength={300}
        />
      </label>
      <fieldset>
        <legend>در کدام دسته بماند؟</legend>
        <div className="category-choices">
          {categories.map((c) => (
            <label key={c.id} className={ids.includes(c.id) ? "checked" : ""}>
              <input
                type="checkbox"
                checked={ids.includes(c.id)}
                onChange={() =>
                  setIds((old) =>
                    old.includes(c.id)
                      ? old.filter((i) => i !== c.id)
                      : [...old, c.id],
                  )
                }
              />
              {c.symbol} {c.name}
            </label>
          ))}
        </div>
        {!categories.length && <p>ابتدا از بخش «دسته‌های من» یک دسته بساز.</p>}
      </fieldset>
      <label>
        یادداشت
        <textarea
          name="note"
          rows={3}
          defaultValue={video?.note || ""}
          maxLength={3000}
          placeholder="چرا می‌خواهی دوباره ببینی‌اش؟"
        />
      </label>
      {message && (
        <p className="inline-error" role="alert">
          {message}
        </p>
      )}
      <button className="primary-button" disabled={busy || !ids.length}>
        {busy
          ? "در حال ذخیره…"
          : video
            ? "ذخیرهٔ تغییرات"
            : "ذخیره و دریافت ویدیو"}
      </button>
      {video && (
        <div className="edit-actions">
          <button
            type="button"
            disabled={busy || video.status !== "ready"}
            onClick={() => onDownload(video)}
          >
            <Download size={17} />
            دانلود ویدیو
          </button>
          {video.audio_url && (
            <button type="button" onClick={() => onDownload(video, "audio")}>
              <Headphones size={17} />
              دانلود صدا
            </button>
          )}
          <button
            className="danger"
            type="button"
            disabled={busy || video.status === "downloading"}
            onClick={async () => {
              if (!confirm("این ویدیو از آرشیوت حذف شود؟")) return;
              setBusy(true);
              try {
                await api(`videos/${video.id}/`, { method: "DELETE" });
                onDelete(video);
              } catch (e) {
                setMessage((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Trash2 size={17} />
            حذف از آرشیو
          </button>
        </div>
      )}
    </form>
  );
}
