/* One audio element survives feed changes and hands playback to the OS media session. */
(() => {
  const player = document.querySelector('[data-audio-player]');
  if (!player) return;
  const audio = player.querySelector('audio');
  const title = player.querySelector('[data-audio-title]');
  const collection = player.querySelector('[data-audio-collection]');
  const status = player.querySelector('[data-audio-status]');
  const toggle = player.querySelector('[data-audio-toggle]');
  const previous = player.querySelector('[data-audio-previous]');
  const next = player.querySelector('[data-audio-next]');
  const seek = player.querySelector('[data-audio-seek]');
  let prepared = null;
  let queue = [];
  let index = 0;
  let enabled = false;
  let generation = 0;
  let fetchController;
  let playbackRevision = 0;
  let recoveryAttempts = 0;
  let recoveryPosition = null;
  const session = navigator.mediaSession;
  const time = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

  async function prepare() {
    const launcher = document.querySelector('[data-audio-launch]');
    if (!launcher) return;
    const button = launcher.querySelector('[data-audio-start]');
    const hint = launcher.querySelector('[data-audio-hint]');
    launcher.hidden = false;
    button.disabled = true;
    button.textContent = 'آماده‌سازی فهرست…';
    prepared = null;
    const revision = ++generation;
    fetchController?.abort();
    const controller = fetchController = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(launcher.dataset.playlistUrl, {signal: controller.signal, cache: 'no-store'});
      if (!response.ok || response.redirected) throw new Error('playlist');
      const result = await response.json();
      if (revision !== generation) return;
      prepared = result;
      button.textContent = result.tracks.length ? `پخش صوتی پیوسته · ${result.tracks.length} ویدیو` : 'صدایی برای پخش نیست';
      button.disabled = !result.tracks.length;
      hint.textContent = [
        result.tracks.length ? 'صدای ویدیوهای این انتخاب، پشت سر هم.' : '',
        result.pending ? `${result.pending} ویدیو هنوز نسخهٔ صوتی ندارد.` : '',
        result.silent ? `${result.silent} ویدیوی بی‌صدا از فهرست کنار گذاشته شد.` : '',
      ].filter(Boolean).join(' ');
    } catch (_) {
      if (revision !== generation) return;
      button.disabled = false;
      button.textContent = 'تلاش دوباره برای فهرست صوتی';
      hint.textContent = 'فهرست دریافت نشد؛ اتصال و ورود به حساب را بررسی کن.';
    } finally { clearTimeout(timeout); }
  }
  function setMode(value) {
    enabled = value;
    player.hidden = !value;
    document.body.classList.toggle('audio-mode', value);
    // Experimental on some browsers; the standard audio player remains the fallback.
    try { if (navigator.audioSession) navigator.audioSession.type = value ? 'playback' : 'auto'; } catch (_) {}
    document.dispatchEvent(new CustomEvent('playlist-mode', {detail: {enabled: value}}));
  }
  function position() {
    const duration = audio.duration;
    const valid = Number.isFinite(duration) && duration > 0;
    seek.disabled = !valid;
    seek.max = valid ? duration : 100;
    seek.value = valid ? audio.currentTime : 0;
    player.querySelector('[data-audio-time]').textContent = `${time(audio.currentTime || 0)} / ${time(valid ? duration : 0)}`;
    if (enabled && valid && session?.setPositionState) {
      try { session.setPositionState({duration, playbackRate: audio.playbackRate, position: Math.min(audio.currentTime, duration)}); } catch (_) {}
    }
  }
  function controls() {
    toggle.textContent = audio.paused ? 'پخش' : 'توقف';
    toggle.setAttribute('aria-label', audio.paused ? 'پخش صدا' : 'توقف صدا');
    previous.disabled = index === 0;
    next.disabled = index >= queue.length - 1;
    if (session && enabled) session.playbackState = audio.paused ? 'paused' : 'playing';
  }
  function play() {
    if (!enabled) return;
    const revision = ++playbackRevision;
    status.textContent = '';
    // Called directly in the initiating click, with an already fetched playlist.
    audio.play().catch(error => {
      if (revision !== playbackRevision || !enabled || error.name === 'AbortError') return;
      status.textContent = error.name === 'NotAllowedError' ? 'برای ادامه، دکمهٔ پخش را بزن.' : 'پخش ممکن نشد؛ دوباره پخش را بزن یا به صدای بعدی برو.';
      controls();
    });
  }
  function loadTrack(target) {
    if (!enabled || target < 0 || target >= queue.length) return;
    recoveryAttempts = 0;
    recoveryPosition = null;
    index = target;
    const track = queue[index];
    title.textContent = track.title;
    collection.textContent = `${queue.label} · ${index + 1} از ${queue.length}`;
    audio.src = track.url;
    if (session && 'MediaMetadata' in window) {
      session.metadata = new MediaMetadata({title: track.title, artist: 'حالِ خوب', album: queue.label,
        artwork: track.artwork ? [{src: new URL(track.artwork, location.href).href, type: 'image/jpeg'}] : []});
    }
    controls();
    position();
    play();
  }
  function stop() {
    if (!enabled) return;
    ++playbackRevision;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    if (session) {
      session.playbackState = 'none';
      session.metadata = null;
      try { session.setPositionState?.(); } catch (_) {}
      for (const action of Object.keys(handlers)) { try { session.setActionHandler(action, null); } catch (_) {} }
    }
    setMode(false);
  }
  function seekTo(seconds) {
    if (enabled && Number.isFinite(audio.duration)) audio.currentTime = Math.max(0, Math.min(seconds, audio.duration));
  }
  const handlers = {
    play, pause: () => audio.pause(), stop,
    previoustrack: () => loadTrack(index - 1), nexttrack: () => loadTrack(index + 1),
    seekto: event => seekTo(event.seekTime),
    seekbackward: event => seekTo(audio.currentTime - (event.seekOffset || 10)),
    seekforward: event => seekTo(audio.currentTime + (event.seekOffset || 10)),
  };
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-audio-start]')) return;
    if (!prepared) { prepare(); return; }
    if (!prepared.tracks.length) return;
    queue = prepared.tracks.slice();
    queue.label = prepared.label;
    setMode(true);
    if (session) for (const [action, handler] of Object.entries(handlers)) {
      try { session.setActionHandler(action, handler); } catch (_) {}
    }
    loadTrack(0);
  });
  toggle.addEventListener('click', () => {
    if (audio.error) {
      recoveryAttempts = 0;
      recoveryPosition = audio.currentTime || 0;
      audio.src = queue[index].url + '?renew=' + Date.now();
    }
    if (audio.paused) play(); else audio.pause();
  });
  previous.addEventListener('click', () => loadTrack(index - 1));
  next.addEventListener('click', () => loadTrack(index + 1));
  player.querySelector('[data-audio-close]').addEventListener('click', () => {
    stop();
    document.querySelector('[data-audio-start]')?.focus({preventScroll: true});
  });
  seek.addEventListener('input', () => seekTo(Number(seek.value)));
  audio.addEventListener('play', controls);
  audio.addEventListener('pause', controls);
  audio.addEventListener('timeupdate', position);
  audio.addEventListener('loadedmetadata', () => {
    if (recoveryPosition !== null) { seekTo(recoveryPosition); recoveryPosition = null; }
    position();
  });
  audio.addEventListener('ended', () => {
    if (!enabled) return;
    if (index < queue.length - 1) loadTrack(index + 1);
    else { status.textContent = 'فهرست به پایان رسید.'; controls(); }
  });
  audio.addEventListener('error', () => {
    if (enabled && recoveryAttempts++ === 0) {
      recoveryPosition = audio.currentTime || 0;
      const url = new URL(queue[index].url, location.href);
      url.searchParams.set('renew', Date.now());
      audio.src = url.href;
      play();
      return;
    }
    if (enabled) status.textContent = 'این صدا در دسترس نیست؛ دوباره پخش را بزن یا به صدای بعدی برو.';
  });
  document.addEventListener('playlist-stop', stop);
  document.addEventListener('playlist-filter-change', prepare);
  // Visibility changes deliberately do not pause audio. Closing/navigating away does.
  window.addEventListener('pagehide', stop);
  prepare();
})();
