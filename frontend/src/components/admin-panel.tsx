"use client";
import { useAuth, UserButton } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, RefreshCw, Search, ShieldCheck, LoaderCircle } from "lucide-react";
import { bytes } from "@/lib/types";
import ActionButton from "./action-button";
import BrandMark from "./brand-mark";

type Counts = Record<string, number>;
type User = {
  id: number;
  name: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  joined_at: string;
  storage_used: number;
  storage_limit: number;
  videos: Counts;
};
type Users = { items: User[]; page: number; pages: number; count: number };
type Overview = {
  host: null | {
    timestamp: number;
    stale: boolean;
    cpu_percent: number;
    cpu_count: number;
    memory_total: number;
    memory_used: number;
    disk_total: number;
    disk_used: number;
    disk_free: number;
    uptime_seconds: number;
    services: Record<string, { running: boolean; health: string }>;
  };
  database_ms: number;
  worker_online: boolean;
  users: number;
  storage_used: number;
  storage_allocated: number;
  default_storage_limit: number;
  videos: Counts;
  sampled_at: string;
  quota_changes: {
    id: number;
    actor: string;
    user: string;
    old_limit: number;
    new_limit: number;
    created_at: string;
  }[];
};
const number = (n: number) =>
  n.toLocaleString("fa-IR", { maximumFractionDigits: 1 });
const date = (value: string) => new Date(value).toLocaleString("fa-IR");
const states: Record<string, string> = {
  ready: "آماده",
  queued: "در صف",
  downloading: "در حال دریافت",
  failed: "ناموفق",
};
const serviceNames: Record<string, string> = {
  web: "API",
  frontend: "سایت",
  worker: "پردازشگر",
  db: "دیتابیس",
  gateway: "درگاه",
};

function UserCard({
  user,
  save,
}: {
  user: User;
  save: (id: number, limit: number) => Promise<User>;
}) {
  const [limit, setLimit] = useState(String(user.storage_limit / 1e9));
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  useEffect(
    () => setLimit(String(user.storage_limit / 1e9)),
    [user.storage_limit],
  );
  const proposed = Math.round(Number(limit) * 1e9);
  return (
    <article className="admin-user">
      <header>
        <div>
          <h3>{user.name}</h3>
          <p className="admin-email" dir="ltr">
            {user.email}
          </p>
        </div>
        <span className="admin-badge">
          {user.is_admin ? "مدیر" : "کاربر"}
          {!user.is_active && " · غیرفعال"}
        </span>
      </header>
      <p>عضویت: {date(user.joined_at)}</p>
      <div className="admin-counts">
        {Object.entries(states).map(([key, label]) => (
          <span key={key}>
            {label}: {number(user.videos[key] || 0)}
          </span>
        ))}
      </div>
      <progress
        aria-label={`مصرف فضای ${user.name}`}
        max={user.storage_limit || 1}
        value={Math.min(user.storage_used, user.storage_limit || 1)}
      />
      <p>
        {bytes(user.storage_used)} مصرف‌شده از {bytes(user.storage_limit)}
      </p>
      {user.storage_used >= user.storage_limit && (
        <p className="admin-warning">
          فضای کافی برای دریافت تازه ندارد؛ فایل‌های قبلی حفظ می‌شوند.
        </p>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setMessage("");
          if (
            !limit.trim() ||
            !Number.isSafeInteger(proposed) ||
            proposed < 0 ||
            proposed > 1e15
          ) {
            setMessage("سهمیهٔ معتبر وارد کن.");
            return;
          }
          setBusy(true);
          try {
            await save(user.id, proposed);
            setMessage("سهمیه ذخیره شد.");
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor={`quota-${user.id}`}>سهمیهٔ فضا (گیگابایت)</label>
        <div className="admin-quota-input">
          <input
            id={`quota-${user.id}`}
            type="number"
            min="0"
            max="1000000"
            step="any"
            inputMode="decimal"
            dir="ltr"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            required
          />
          <button className="primary-button" disabled={busy}>
            {busy && <LoaderCircle className="spin" size={18} />}{busy ? "در حال ذخیره…" : "ذخیرهٔ سهمیه"}
          </button>
        </div>
        {limit.trim() && proposed < user.storage_used && (
          <small className="admin-warning">
            این سهمیه کمتر از مصرف فعلی است؛ دریافت تازه متوقف می‌شود.
          </small>
        )}
        <p className="admin-feedback" role="status">
          {message}
        </p>
      </form>
    </article>
  );
}

export default function AdminPanel() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [overview, setOverview] = useState<Overview | null>(null),
    [users, setUsers] = useState<Users | null>(null);
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(1);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [usersLoading, setUsersLoading] = useState(false);
  const request = useCallback(
    async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
      let token = await getToken();
      const send = () =>
        fetch("/api/v1/admin/" + path, {
          ...options,
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + token,
          },
        });
      let response = await send();
      if (response.status === 401) {
        token = await getToken({ skipCache: true });
        response = await send();
      }
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 403 || response.status === 401) {
          setOverview(null);
          setUsers(null);
        }
        throw new Error(data.error?.message || "ارتباط با سرور برقرار نشد.");
      }
      return data;
    },
    [getToken],
  );
  const refresh = useCallback(async () => {
    try {
      setOverview(await request<Overview>("overview/"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [request]);
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 30000);
    return () => clearInterval(timer);
  }, [isLoaded, isSignedIn, refresh]);
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    setUsersLoading(true);
    request<Users>(`users/?q=${encodeURIComponent(query)}&page=${page}`)
      .then((data) => {
        if (!cancelled) setUsers(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setUsersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request, query, page, isLoaded, isSignedIn]);
  const host = overview?.host;
  return (
    <main className="admin-page">
      <header className="admin-header">
        <a className="brand" href="/">
          <BrandMark size={34} />
          حال‌خوب
        </a>
        <a href="/" className="admin-back">
          <ArrowRight size={18} />
          بازگشت به آرشیو
        </a>
        <UserButton />
      </header>
      <div className="admin-heading">
        <div>
          <span className="eyebrow">مدیریت حال‌خوب</span>
          <h1>
            <ShieldCheck />
            وضعیت سیستم و کاربران
          </h1>
          <p>هر کاربر، فضای خودش. بدون محدودیت مدت و تعداد دریافت ویدیو.</p>
        </div>
        <ActionButton
          className="admin-refresh"
          onAction={refresh}
          aria-label="به‌روزرسانی وضعیت"
        >
          <RefreshCw size={18} />
          به‌روزرسانی
        </ActionButton>
      </div>
      {error && (
        <p className="admin-warning" role="alert">
          {error}
        </p>
      )}
      {loading && <p role="status">در حال بررسی دسترسی و دریافت اطلاعات…</p>}
      {overview && (
        <>
          <section aria-labelledby="server-heading">
            <h2 id="server-heading">سرور</h2>
            <p className="admin-muted">
              به‌روزرسانی خودکار هر ۳۰ ثانیه · آخرین دریافت:{" "}
              {date(overview.sampled_at)}
            </p>
            {!host ? (
              <p className="admin-warning">
                اطلاعات منابع سرور هنوز در دسترس نیست.
              </p>
            ) : (
              <>
                {host.stale && (
                  <p role="status" className="admin-warning">
                    نمونهٔ منابع سرور قدیمی است؛ وضعیت نمایش‌داده‌شده لحظه‌ای
                    نیست.
                  </p>
                )}
                <div className="admin-stats">
                  <article>
                    <span>پردازندهٔ سرور</span>
                    <strong>{number(host.cpu_percent)}٪</strong>
                    <small>{number(host.cpu_count)} هسته</small>
                  </article>
                  <article>
                    <span>حافظهٔ سرور</span>
                    <strong>{bytes(host.memory_used)}</strong>
                    <small>از {bytes(host.memory_total)}</small>
                    <progress
                      aria-label="مصرف حافظهٔ سرور"
                      value={host.memory_used}
                      max={host.memory_total}
                    />
                  </article>
                  <article>
                    <span>دیسک سرور</span>
                    <strong>{bytes(host.disk_free)} آزاد</strong>
                    <small>
                      {bytes(host.disk_used)} مصرف‌شده از{" "}
                      {bytes(host.disk_total)}
                    </small>
                    <progress
                      aria-label="مصرف دیسک سرور"
                      value={host.disk_used}
                      max={host.disk_total}
                    />
                  </article>
                  <article>
                    <span>زمان روشن‌بودن سرور</span>
                    <strong>{number(host.uptime_seconds / 86400)} روز</strong>
                    <small>
                      نمونه:{" "}
                      {new Date(host.timestamp * 1000).toLocaleTimeString(
                        "fa-IR",
                      )}
                    </small>
                  </article>
                </div>
                <p className="admin-muted">
                  منابع مربوط به کل سرور هستند، شامل سایت‌های دیگری که روی آن
                  اجرا می‌شوند.
                </p>
                <div className="admin-services">
                  {Object.entries(host.services).map(([name, s]) => (
                    <span
                      className={
                        s.running && ["healthy", "unknown"].includes(s.health)
                          ? "admin-ok"
                          : "admin-warning"
                      }
                      key={name}
                    >
                      {serviceNames[name] || name}:{" "}
                      {s.running
                        ? s.health === "unhealthy"
                          ? "نیازمند بررسی"
                          : s.health === "starting"
                            ? "در حال شروع"
                            : "در حال اجرا"
                        : "متوقف / نامشخص"}
                    </span>
                  ))}
                </div>
              </>
            )}
            <div className="admin-services">
              <span className="admin-ok">
                دیتابیس پاسخ می‌دهد · {number(overview.database_ms)} میلی‌ثانیه
              </span>
              <span
                className={
                  overview.worker_online ? "admin-ok" : "admin-warning"
                }
              >
                ارتباط پردازشگر:{" "}
                {overview.worker_online ? "فعال" : "قطع / نامشخص"}
              </span>
            </div>
          </section>
          <section aria-labelledby="archive-heading">
            <h2 id="archive-heading">آرشیو و دریافت‌ها</h2>
            <div className="admin-stats">
              <article>
                <span>کاربران</span>
                <strong>{number(overview.users)}</strong>
                <small>
                  سهمیهٔ حساب تازه: {bytes(overview.default_storage_limit)}
                </small>
              </article>
              <article>
                <span>فایل‌های ذخیره‌شده</span>
                <strong>{bytes(overview.storage_used)}</strong>
                <small>شامل فایل‌های در انتظار پاک‌سازی</small>
              </article>
              <article>
                <span>مجموع سهمیه‌های کاربران</span>
                <strong>{bytes(overview.storage_allocated)}</strong>
                <small>مقدار تخصیص‌یافته؛ فضای مصرف‌شده نیست</small>
              </article>
              <article>
                <span>وضعیت ویدیوها</span>
                {Object.entries(states).map(([key, label]) => (
                  <small key={key}>
                    {label}: {number(overview.videos[key] || 0)}
                  </small>
                ))}
              </article>
            </div>
          </section>
          <section aria-labelledby="users-heading">
            <h2 id="users-heading">کاربران و سهمیه‌ها</h2>
            <p className="admin-muted">
              هر گیگابایت برابر یک میلیارد بایت است. صفر، دریافت جدید را متوقف
              می‌کند. کاهش سهمیه فایل‌های قبلی را پاک نمی‌کند. فضای فایل‌های
              حذف‌شده پس از پاک‌سازی دوره‌ای آزاد می‌شود.
            </p>
            <form
              className="admin-search"
              onSubmit={(e) => {
                e.preventDefault();
                setPage(1);
                setQuery(search.trim());
              }}
            >
              <label className="sr-only" htmlFor="admin-search">
                جست‌وجوی نام یا ایمیل
              </label>
              <input
                id="admin-search"
                placeholder="جست‌وجوی نام یا ایمیل…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <button aria-label="جست‌وجوی کاربران" disabled={usersLoading} aria-busy={usersLoading}>
                {usersLoading && <LoaderCircle className="spin" size={18} />}
                <Search size={20} />
              </button>
            </form>
            {usersLoading && <p role="status">در حال دریافت کاربران…</p>}
            {!usersLoading && users && (
              <>
                <p>{number(users.count)} کاربر</p>
                <div className="admin-users">
                  {users.items.map((user) => (
                    <UserCard
                      key={user.id}
                      user={user}
                      save={async (id, limit) => {
                        const updated = await request<User>(
                          `users/${id}/quota/`,
                          {
                            method: "PATCH",
                            body: JSON.stringify({ storage_limit: limit }),
                          },
                        );
                        setUsers((current) =>
                          current
                            ? {
                                ...current,
                                items: current.items.map((u) =>
                                  u.id === id ? updated : u,
                                ),
                              }
                            : current,
                        );
                        void refresh();
                        return updated;
                      }}
                    />
                  ))}
                </div>
                {users.count === 0 && <p>کاربری با این مشخصات پیدا نشد.</p>}
                <nav
                  className="admin-pagination"
                  aria-label="صفحه‌بندی کاربران"
                >
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    قبلی
                  </button>
                  <span>
                    {number(users.page)} از {number(users.pages)}
                  </span>
                  <button
                    disabled={page >= users.pages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    بعدی
                  </button>
                </nav>
              </>
            )}
          </section>
          <section aria-labelledby="history-heading">
            <h2 id="history-heading">آخرین تغییرات سهمیه</h2>
            {overview.quota_changes.length === 0 ? (
              <p className="admin-muted">هنوز تغییری ثبت نشده است.</p>
            ) : (
              <ol className="admin-history">
                {overview.quota_changes.map((change) => (
                  <li key={change.id}>
                    <b dir="ltr">{change.user}</b>
                    <span>
                      {bytes(change.old_limit)} ← {bytes(change.new_limit)}
                    </span>
                    <small>
                      توسط <bdi>{change.actor}</bdi> · {date(change.created_at)}
                    </small>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </main>
  );
}
