document.documentElement.classList.add('js');
const menu = document.querySelector('.mobile-menu');
if (menu) {
  menu.addEventListener('click', () => {
    const open = document.querySelector('.sidebar').classList.toggle('is-open');
    menu.setAttribute('aria-expanded', String(open));
  });
}
document.querySelectorAll('form[data-submit]').forEach(form => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('[aria-busy="true"]').forEach(button => {
    button.disabled = false; button.removeAttribute('aria-busy');
  });
});
const panel = document.querySelector('[data-status-url]');
if (panel && ['queued', 'downloading'].includes(panel.dataset.initialStatus)) {
  let failures = 0;
  const poll = async () => {
    if (document.hidden) { setTimeout(poll, 5000); return; }
    try {
      const response = await fetch(panel.dataset.statusUrl, {headers: {'Accept': 'application/json'}, signal: AbortSignal.timeout(10000)});
      if (response.redirected) { location.assign('/login/'); return; }
      if (response.status === 404) { location.assign('/archive/'); return; }
      if (!response.ok) throw new Error('status');
      const state = await response.json();
      failures = 0;
      if (['ready', 'failed'].includes(state.status)) { location.reload(); return; }
      panel.querySelector('[data-status-label]').textContent = state.label;
      panel.querySelector('progress').value = state.progress;
      panel.querySelector('[data-status-error]').textContent = state.error || 'دریافت در پس‌زمینه ادامه دارد؛ می‌توانی صفحه را ببندی.';
      panel.querySelector('[data-connection-status]').textContent = '';
    } catch (_) {
      failures += 1;
      panel.querySelector('[data-connection-status]').textContent = 'ارتباط این صفحه قطع شده؛ وضعیت را دوباره بررسی می‌کنیم.';
    }
    setTimeout(poll, Math.min(30000, 2500 * (failures + 1)));
  };
  setTimeout(poll, 1500);
}
