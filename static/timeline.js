/* One visible player, progressively enhanced filters and an append-only timeline. */
(() => {
  const root = document.querySelector('[data-timeline]');
  if (!root) return;
  const announcement = document.querySelector('[data-feed-announcement]');
  let active = null;
  let sound = false;
  let suspended = false;
  let audioMode = false;
  let frame = 0;
  let request = null;
  let revision = 0;
  let loadingMore = false;
  let nextObserver;
  let navigationURL = location.href;
  const pausedByUser = new WeakSet();
  const mounted = new WeakSet();
  const candidates = new Set();

  function notice(video, message) {
    video.closest('[data-post-id]').querySelector('[data-post-notice]').textContent = message;
  }
  function pauseAll() {
    active = null; // pause events from our own transitions must not count as user input.
    root.querySelectorAll('[data-feed-video]').forEach(video => video.pause());
  }
  function visible(video) {
    const rect = video.getBoundingClientRect();
    const top = 64;
    const shown = Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, top));
    return shown / Math.max(1, rect.height) >= 0.55;
  }
  function soundLabels() {
    root.querySelectorAll('[data-feed-sound]').forEach(button => {
      const video = button.closest('[data-post-id]').querySelector('video');
      button.setAttribute('aria-pressed', String(!video.muted));
      button.setAttribute('aria-label', video.muted ? 'روشن کردن صدا' : 'خاموش کردن صدا');
    });
  }
  function playbackLabel(video) {
    const media = video.closest('.post-media');
    media.classList.toggle('is-playing', !video.paused);
    media.querySelector('[data-feed-play]').setAttribute('aria-label', video.paused ? 'پخش ویدیو' : 'توقف ویدیو');
  }
  async function start(video) {
    if (document.hidden || suspended || audioMode || !video.isConnected || !visible(video)) return;
    if (active !== video) { pauseAll(); active = video; }
    video.muted = !sound;
    soundLabels();
    try {
      await video.play();
    } catch (_) {
      if (active !== video || !video.isConnected || document.hidden || suspended || audioMode) return;
      if (pausedByUser.has(video)) return;
      // Some browsers require a gesture for each new audible media element.
      if (!video.muted) {
        video.muted = true;
        soundLabels();
        try { await video.play(); } catch (_) { pausedByUser.add(video); }
      } else { pausedByUser.add(video); }
      if (video.paused) notice(video, 'برای شروع، دکمهٔ پخش ویدیو را بزن.');
    }
    if (active !== video || document.hidden || suspended || audioMode || !visible(video)) video.pause();
  }
  function choose() {
    frame = 0;
    if (document.hidden || suspended || audioMode) { pauseAll(); return; }
    let best = null;
    let distance = Infinity;
    for (const video of candidates) {
      if (!video.isConnected) { candidates.delete(video); continue; }
      if (!visible(video)) { pausedByUser.delete(video); continue; }
      const rect = video.getBoundingClientRect();
      const nextDistance = Math.abs((rect.top + rect.bottom) / 2 - (innerHeight + 64) / 2);
      if (nextDistance < distance) { best = video; distance = nextDistance; }
    }
    if (best !== active) {
      pauseAll();
      if (best && !pausedByUser.has(best)) start(best);
    }
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(choose); }
  const observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) candidates.add(entry.target);
      else { candidates.delete(entry.target); pausedByUser.delete(entry.target); }
    }
    schedule();
  }, {threshold: [0, 0.25, 0.55, 0.75, 1]}) : null;

  function mount() {
    root.querySelectorAll('[data-feed-video]').forEach(video => {
      if (mounted.has(video)) return;
      mounted.add(video);
      const mediaURL = video.getAttribute("src");
      let recoveryAttempts = 0;
      let recoveryPosition = null;
      video.addEventListener("loadedmetadata", () => {
        if (recoveryPosition !== null) { video.currentTime = recoveryPosition; recoveryPosition = null; }
      });
      video.controls = false;
      video.closest('.post-media').setAttribute('data-custom-player', '');
      playbackLabel(video);
      video.muted = !sound;
      if (observer) observer.observe(video); else candidates.add(video);
      video.addEventListener('play', () => {
        if (document.hidden || suspended || audioMode || !visible(video)) { video.pause(); return; }
        if (active !== video) { pauseAll(); active = video; }
        pausedByUser.delete(video);
        playbackLabel(video);
        notice(video, '');
      });
      video.addEventListener('pause', () => {
        if (active === video && !document.hidden && !suspended) pausedByUser.add(video);
        playbackLabel(video);
      });
      video.addEventListener('volumechange', soundLabels);
      video.addEventListener('error', () => {
        if (recoveryAttempts++ === 0) {
          recoveryPosition = video.currentTime || 0;
          const url = new URL(mediaURL, location.href);
          url.searchParams.set('renew', Date.now());
          video.src = url.href;
          if (active === video) start(video);
          return;
        }
        pausedByUser.add(video);
        notice(video, 'پخش فایل ممکن نشد؛ اتصال را بررسی کن و دوباره صفحه را باز کن.');
      });
    });
    soundLabels();
    nextObserver?.disconnect();
    const next = root.querySelector('[data-feed-next]');
    if (next && 'IntersectionObserver' in window) {
      nextObserver = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) loadMore();
      }, {rootMargin: '0px 0px 350px 0px'});
      nextObserver.observe(next);
    }
    schedule();
  }
  async function getFragment(url, signal) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort, {once: true});
    if (signal?.aborted) controller.abort();
    const timeout = setTimeout(abort, 15000);
    try {
      const response = await fetch(url, {headers: {'X-Timeline': 'fragment'}, signal: controller.signal});
      if (response.redirected) { location.assign(response.url); throw new Error('login'); }
      if (!response.ok) throw new Error('request');
      return new DOMParser().parseFromString(await response.text(), 'text/html');
    } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
  }
  async function navigate(url, history = true) {
    const destination = new URL(url, location.href);
    if (destination.origin !== location.origin) return;
    const currentRevision = ++revision;
    request?.abort();
    request = new AbortController();
    loadingMore = false;
    nextObserver?.disconnect();
    suspended = true;
    pauseAll();
    root.setAttribute('aria-busy', 'true');
    announcement.textContent = 'در حال دریافت ویدیوها…';
    try {
      const fragment = await getFragment(destination, request.signal);
      if (currentRevision !== revision) return;
      observer?.disconnect();
      candidates.clear();
      root.replaceChildren(...Array.from(fragment.body.childNodes));
      navigationURL = destination.href;
      document.querySelectorAll('.main-nav a').forEach(link => {
        const target = new URL(link.href);
        const selected = target.pathname === destination.pathname && target.searchParams.get('filter') === destination.searchParams.get('filter');
        if (selected) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
      });
      document.querySelector('.sidebar')?.classList.remove('is-open');
      document.querySelector('.mobile-menu')?.setAttribute('aria-expanded', 'false');
      if (history) window.history.pushState({}, '', destination);
      suspended = false;
      mount();
      document.dispatchEvent(new Event('playlist-filter-change'));
      root.scrollIntoView({block: 'start', behavior: 'instant'});
      root.querySelector('#collection-title').focus({preventScroll: true});
      announcement.textContent = 'ویدیوهای این انتخاب نمایش داده شدند.';
    } catch (error) {
      if (currentRevision !== revision) return;
      if (!history) window.history.replaceState({}, '', navigationURL);
      announcement.textContent = 'دریافت ویدیوها ممکن نشد؛ انتخاب قبلی حفظ شد. دوباره امتحان کن.';
    } finally {
      if (currentRevision === revision) {
        suspended = false;
        root.removeAttribute('aria-busy');
        schedule();
      }
    }
  }
  async function loadMore() {
    const next = root.querySelector('[data-feed-next]');
    if (!next || loadingMore || suspended) return;
    loadingMore = true;
    const currentRevision = revision;
    next.setAttribute('aria-busy', 'true');
    next.textContent = 'در حال دریافت…';
    try {
      const fragment = await getFragment(next.href);
      if (currentRevision !== revision) return;
      const existing = new Set(Array.from(root.querySelectorAll('[data-post-id]'), post => post.dataset.postId));
      fragment.querySelectorAll('[data-post-id]').forEach(post => {
        if (!existing.has(post.dataset.postId)) root.querySelector('[data-feed-posts]').append(post);
      });
      root.querySelector('[data-feed-pagination]').replaceWith(fragment.querySelector('[data-feed-pagination]'));
      root.querySelector('.feed-previous')?.remove();
      mount();
    } catch (_) {
      if (currentRevision !== revision) return;
      nextObserver?.disconnect(); // retry is explicit, rather than an endless failing loop.
      next.textContent = 'تلاش دوباره برای ویدیوهای بیشتر';
      next.removeAttribute('aria-busy');
      announcement.textContent = 'دریافت ادامهٔ آرشیو ممکن نشد؛ ویدیوهای فعلی در دسترس‌اند.';
    } finally { if (currentRevision === revision) loadingMore = false; }
  }
  root.addEventListener('click', event => {
    const link = event.target.closest('a[data-feed-filter], a[data-feed-next]');
    if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
      event.preventDefault();
      if (link.hasAttribute('data-feed-next')) loadMore(); else navigate(link.href);
      return;
    }
    const playback = event.target.closest('[data-feed-play]');
    if (playback) {
      const video = playback.closest('.post-media').querySelector('video');
      if (video.paused) {
        document.dispatchEvent(new Event('playlist-stop'));
        pausedByUser.delete(video); start(video);
      }
      else { pausedByUser.add(video); video.pause(); }
      playbackLabel(video);
      return;
    }
    const button = event.target.closest('[data-feed-sound]');
    if (button) {
      const video = button.closest('[data-post-id]').querySelector('video');
      sound = video.muted;
      root.querySelectorAll('[data-feed-video]').forEach(item => { item.muted = !sound; });
      soundLabels();
    }
  });
  root.addEventListener('submit', async event => {
    const form = event.target;
    if (form.matches('[data-feed-search]')) {
      event.preventDefault();
      const url = new URL(form.action);
      url.search = new URLSearchParams(new FormData(form));
      navigate(url);
    } else if (form.matches('[data-feed-favorite]')) {
      event.preventDefault();
      const button = form.querySelector('button');
      const post = form.closest('[data-post-id]');
      button.disabled = true;
      try {
        const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json'}});
        if (response.redirected) { location.assign(response.url); return; }
        if (!response.ok) throw new Error('favorite');
        const result = await response.json();
        button.setAttribute('aria-pressed', String(result.favorite));
        button.querySelector('[data-heart]').textContent = result.favorite ? '♥' : '♡';
        document.dispatchEvent(new Event('playlist-filter-change'));
        post.querySelector('[data-post-notice]').textContent = result.favorite ? 'به دوست‌داشتنی‌ها اضافه شد.' : 'از دوست‌داشتنی‌ها برداشته شد.';
      } catch (_) { post.querySelector('[data-post-notice]').textContent = 'ذخیره نشد؛ دوباره امتحان کن.'; }
      finally { button.disabled = false; }
    }
  });
  document.addEventListener('click', event => {
    const link = event.target.closest('.sidebar a');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href);
    if (url.origin === location.origin && ['/', '/archive/'].includes(url.pathname)) {
      event.preventDefault();
      navigate(url);
    }
  });
  document.addEventListener('playlist-mode', event => {
    audioMode = event.detail.enabled;
    if (audioMode) pauseAll(); else schedule();
  });
  window.addEventListener('scroll', schedule, {passive: true});
  window.addEventListener('resize', schedule);
  document.addEventListener('visibilitychange', () => { if (document.hidden) pauseAll(); else schedule(); });
  window.addEventListener('pagehide', pauseAll);
  window.addEventListener('pageshow', schedule);
  window.addEventListener('popstate', () => {
    const previous = new URL(navigationURL);
    if (previous.pathname + previous.search !== location.pathname + location.search) navigate(location.href, false);
  });
  mount();
})();
