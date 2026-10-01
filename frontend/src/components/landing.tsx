"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, Download, Headphones, Heart, Link2, Pause, Play, Repeat2, Volume2 } from "lucide-react";
import BrandMark from "./brand-mark";
import styles from "./landing.module.css";

const steps = [
  { label: "لینک بده", title: "یک لینک، شروع آرشیوت.", text: "لینک ویدیوی یوتیوب یا اینستاگرام را اضافه کن. دانلود در پس‌زمینه انجام می‌شود؛ لازم نیست صفحه را باز نگه داری." },
  { label: "مرتب کن", title: "هر ویدیو، سر جای خودش.", text: "دسته‌های خودت را بساز، یادداشت بگذار و ویدیوهای محبوبت را نشان کن. از آموزش و موسیقی تا آرامش و انگیزه." },
  { label: "پخش کن", title: "ببین. یا فقط گوش بده.", text: "در همان تایم‌لاین تماشا کن، صدای یک ویدیو یا کل دسته را بشنو و هر وقت خواستی فایل را روی دستگاهت دانلود کن." },
];

function Demo() {
  const [step, setStep] = useState(0);
  const [autoplay, setAutoplay] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(true);
  const [visible, setVisible] = useState(false);
  const [inView, setInView] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [category, setCategory] = useState("آرامش");
  const demo = useRef<HTMLDivElement>(null);
  const running = autoplay && !reducedMotion && visible && inView && !hovered && !focused;

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setReducedMotion(preference.matches);
    const syncVisibility = () => setVisible(!document.hidden);
    syncMotion();
    syncVisibility();
    preference.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.2 });
    if (demo.current) observer.observe(demo.current);
    return () => {
      preference.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(() => setStep((value) => (value + 1) % steps.length), 8000);
    return () => window.clearTimeout(timer);
  }, [running, step]);

  function selectStep(index: number) {
    setStep(index);
    setAutoplay(false);
  }

  return (
    <div ref={demo} className={styles.demo} data-running={running}
      onPointerEnter={(event) => { if (event.pointerType === "mouse") setHovered(true); }}
      onPointerLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false); }}
    >
      <div className={styles.demoTop}>
        <span>یک نگاه به حال‌خوب</span>
        <span className={styles.exampleLabel}>نمایش نمونه</span>
      </div>
      <div className={styles.steps} aria-label="مراحل کار با حال‌خوب">
        {steps.map((item, index) => (
          <button key={item.label} type="button" aria-pressed={step === index} aria-controls="landing-demo-panel" onClick={() => selectStep(index)}>
            <span>{["۱", "۲", "۳"][index]}</span>{item.label}
          </button>
        ))}
      </div>
      <div id="landing-demo-panel" className={styles.demoPanel}>
        <div key={step} className={styles.scene}>
          {step === 0 && (
            <div className={styles.linkScene}>
              <div className={styles.sourceNames}><span>YouTube</span><span>Instagram</span></div>
              <div className={styles.linkField}><Link2 size={20} /><span dir="ltr">youtube.com/watch?v=…</span><Check size={19} /></div>
              <div className={styles.demoDownload}>
                <div className={styles.miniArt} aria-hidden="true"><Play size={22} /></div>
                <div><strong>چند دقیقه برای خودت</strong><span>در حال ذخیره در آرشیو</span></div>
                <Download size={20} />
              </div>
              <div className={styles.downloadTrack} aria-hidden="true"><span /></div>
              <p className={styles.downloadNote}>لینک را یک بار اضافه کن؛ بعداً برگرد و ببین.</p>
            </div>
          )}
          {step === 1 && (
            <div className={styles.archiveScene}>
              <div className={styles.categoryList} aria-label="دسته‌های نمونه">
                {["آرامش", "یادگیری", "انگیزه"].map((name) => <button key={name} type="button" aria-pressed={category === name} onClick={() => { setCategory(name); setAutoplay(false); }}>{name}</button>)}
              </div>
              <div className={styles.archiveItem}><div className={styles.miniArt} aria-hidden="true"><Play size={22} /></div><div><strong>{category === "آرامش" ? "چند دقیقه برای خودت" : category === "یادگیری" ? "یک چیز تازه یاد بگیر" : "از همین امروز شروع کن"}</strong><span>{category} · آرشیو شخصی</span></div><Heart size={20} fill="currentColor" /></div>
              <div className={styles.archiveItem}><div className={styles.miniArt} aria-hidden="true"><Play size={22} /></div><div><strong>{category === "آرامش" ? "صدای یک صبح آرام" : category === "یادگیری" ? "ایده‌ای برای امتحان کردن" : "یک قدم کوچک دیگر"}</strong><span>{category} · آمادهٔ پخش</span></div><Check size={20} /></div>
              <p className={styles.downloadNote}>یک دسته را انتخاب کن تا نمونه‌اش را ببینی.</p>
            </div>
          )}
          {step === 2 && (
            <div className={styles.listenScene}>
              <div className={styles.landscape} aria-hidden="true"><span className={styles.sun} /><span className={styles.hillBack} /><span className={styles.hillFront} /><span className={styles.artCaption}>کمی مکث کن.</span></div>
              <div className={styles.samplePlayer} aria-hidden="true"><Headphones size={19} /><strong>چند دقیقه برای خودت</strong><span dir="ltr">1.5×</span></div>
              <div className={styles.wave} aria-hidden="true">{Array.from({ length: 32 }, (_, index) => <i key={index} style={{ height: `${[12, 24, 18, 34, 22, 40, 16, 28][index % 8]}px`, animationDelay: `${index * -75}ms` }} />)}</div>
              <div className={styles.sampleControls} aria-hidden="true"><Volume2 size={19} /><span><Pause size={21} /></span><Repeat2 size={19} /></div>
            </div>
          )}
        </div>
      </div>
      <div className={styles.demoCaption} aria-live={autoplay ? "off" : "polite"}>
        <h2>{steps[step].title}</h2>
        <p>{steps[step].text}</p>
      </div>
      <div className={styles.demoBottom}>
        <span>نمونهٔ آموزشی؛ دانلود یا پخش واقعی انجام نمی‌شود.</span>
        {!reducedMotion && <button type="button" onClick={() => setAutoplay((value) => !value)} aria-label={autoplay ? "توقف نمایش خودکار" : "شروع نمایش خودکار"}>{autoplay ? <Pause size={16} /> : <Play size={16} />}</button>}
      </div>
    </div>
  );
}

export default function Landing({ signedIn = false }: { signedIn?: boolean }) {
  const destination = signedIn ? "/" : "/sign-up";
  return (
    <div className={styles.landing}>
      <a className={styles.skip} href="#main">رفتن به محتوای صفحه</a>
      <header className={styles.header}>
        <a href="/" className={styles.brand} aria-label="حال‌خوب، صفحهٔ اصلی"><BrandMark size={38} /><span>حال‌خوب</span></a>
        <a className={styles.login} href={signedIn ? "/" : "/sign-in"}>{signedIn ? "آرشیو من" : "ورود"}<ArrowLeft size={18} /></a>
      </header>
      <main id="main">
        <section className={styles.hero} aria-labelledby="landing-title">
          <div className={styles.intro}>
            <p className={styles.lead}>دانلود و آرشیو ویدیوهای یوتیوب و اینستاگرام</p>
            <h1 id="landing-title">ویدیوهای خوب را<br /><span>برای خودت نگه دار.</span></h1>
            <p className={styles.description}>آموزشی که می‌خواهی دوباره ببینی، آهنگی که دوست داری، یا حرفی که حالت را بهتر می‌کند. لینک را بده و همه را در آرشیو شخصی‌ات کنار هم داشته باش.</p>
            <a href={destination} className={styles.primary}>{signedIn ? "رفتن به آرشیو من" : "ساخت آرشیو با گوگل"}<ArrowLeft size={20} /></a>
            <p className={styles.reassurance}>آرشیو و دسته‌های هر کاربر، مخصوص خودش.</p>
            <a href="#possibilities" className={styles.more}>چه کارهایی می‌توانم انجام بدهم؟<span aria-hidden="true">↓</span></a>
          </div>
          <Demo />
        </section>
        <section id="possibilities" className={styles.features} aria-labelledby="features-title">
          <div className={styles.featureIntro}><h2 id="features-title">از یک دانلود ساده<br />تا آرشیوی برای هر روز.</h2><p>حال‌خوب جایی برای چیزهایی است که خودت انتخاب می‌کنی؛ برای یاد گرفتن، لذت بردن یا برگشتن به یک حس خوب.</p></div>
          <div className={styles.featureList}>
            <article><Download size={23} /><div><h3>دانلود کن و همراهت ببر</h3><p>لینک ویدیو را اضافه کن؛ بعد از آماده‌شدن، فایل را روی گوشی یا لپ‌تاپت هم ذخیره کن.</p></div></article>
            <article><Heart size={23} /><div><h3>آرشیوت را به سلیقهٔ خودت بچین</h3><p>دسته‌های شخصی، علاقه‌مندی‌ها و یادداشت‌ها کمک می‌کنند ویدیوی موردنظرت را دوباره پیدا کنی.</p></div></article>
            <article><Play size={23} /><div><h3>همان‌جا تماشا کن</h3><p>در تایم‌لاین ورق بزن، دسته را عوض کن و بدون بازکردن صفحه‌ای دیگر ویدیو ببین.</p></div></article>
            <article><Headphones size={23} /><div><h3>تصویر لازم نیست؟ گوش بده</h3><p>پخش صوتی یک کلیپ یا کل دسته، تکرار و سرعت‌های ۱٫۵، ۲ و ۳ برابر؛ با کنترل زمان پخش.</p></div></article>
          </div>
        </section>
        <section className={styles.questions} aria-labelledby="questions-title">
          <h2 id="questions-title">قبل از اولین لینک</h2>
          <details><summary>حال‌خوب فقط برای ویدیوهای انگیزشی است؟</summary><p>نه. دسته‌ها را خودت می‌سازی: آموزش، موسیقی، ورزش، آشپزی یا هر موضوعی که دوست داری. حال‌خوب یعنی آرشیوی از انتخاب‌های خودت.</p></details>
          <details><summary>هر لینک یوتیوب و اینستاگرامی دانلود می‌شود؟</summary><p>لینک ویدیوهای عمومی پشتیبانی می‌شود. محدودیت‌های پلتفرم یا دسترسی به بعضی ویدیوها می‌تواند مانع دانلود شود؛ نتیجهٔ هر درخواست و امکان تلاش دوباره در آرشیو مشخص است.</p></details>
          <details><summary>برای ذخیره‌سازی محدودیت دارم؟</summary><p>هر حساب سهمیهٔ فضای مشخصی دارد که داخل آرشیو نمایش داده می‌شود. محدودیت بر اساس حجم فایل‌هاست؛ می‌توانی فایل‌های غیرضروری را حذف کنی و فضا را آزاد کنی.</p></details>
        </section>
        <section className={styles.closing} aria-label="شروع استفاده"><h2>با همان ویدیویی شروع کن<br />که نمی‌خواهی گمش کنی.</h2><a href={destination} className={styles.primary}>{signedIn ? "بازکردن آرشیو" : "ساخت آرشیو با گوگل"}<ArrowLeft size={20} /></a></section>
      </main>
      <footer className={styles.footer}><div><a href="/" className={styles.brand}><BrandMark size={30} /><span>حال‌خوب</span></a><p>چیزهای خوب، دم دست.</p></div><a href="https://github.com/itsmohsenjalali/halekhoob" target="_blank" rel="noopener noreferrer">متن‌باز در گیت‌هاب ↗</a></footer>
    </div>
  );
}
