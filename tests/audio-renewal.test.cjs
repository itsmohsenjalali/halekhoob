const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// DOM/media doubles exercise our event handling; no browser or OS playback is simulated.
class Element {
  constructor() { this.listeners = {}; this.children = {}; this.dataset = {}; this.hidden = true; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); }
  emit(type) { this.dispatchEvent({type}); }
  querySelector(selector) { return this.children[selector] ||= new Element(); }
  setAttribute() {}
  focus() {}
}
class Audio extends Element {
  constructor() { super(); this.paused = true; this.currentTime = 0; this.duration = 100; this.playbackRate = 1; this.urls = []; }
  set src(value) { this.urls.push(value); this.currentTime = 0; this.error = null; this.paused = true; }
  get src() { return this.urls.at(-1); }
  play() { this.paused = false; this.emit('play'); return Promise.resolve(); }
  pause() { this.paused = true; this.emit('pause'); }
  removeAttribute() {}
  load() {}
}
async function setup() {
  const document = new Element();
  const window = new Element();
  const player = document.querySelector('[data-audio-player]');
  const launcher = document.querySelector('[data-audio-launch]');
  const audio = player.children.audio = new Audio();
  document.body = {classList: {toggle() {}}};
  launcher.dataset.playlistUrl = '/api/audio-playlist/';
  let playlist = {label: 'امید', tracks: [{title: 'one', url: '/videos/1/media/audio/'}, {title: 'two', url: '/videos/2/media/audio/'}]};
  const context = {document, window, navigator: {}, location: {href: 'https://private.example/'}, URL,
    AbortController, setTimeout, clearTimeout, CustomEvent: class { constructor(type, opts) { this.type = type; this.detail = opts.detail; } },
    fetch: async () => ({ok: true, redirected: false, json: async () => playlist})};
  vm.runInNewContext(fs.readFileSync('static/audio-player.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  document.dispatchEvent({type: 'click', target: {closest: () => true}});
  return {audio, player, document, setPlaylist: value => { playlist = value; }};
}
test('expired audio URL is renewed once, with playback position restored', async () => {
  const {audio, player} = await setup();
  audio.currentTime = 37;
  audio.error = {code: 2};
  audio.emit('error');
  assert.match(audio.src, /^https:\/\/private.example\/videos\/1\/media\/audio\/\?renew=\d+$/);
  audio.emit('loadedmetadata');
  assert.equal(audio.currentTime, 37);
  assert.equal(audio.paused, false);
  audio.error = {code: 2};
  audio.emit('error');
  assert.equal(audio.urls.length, 2); // Bounded automatic retry, no failure loop.
  assert.ok(player.querySelector('[data-audio-status]').textContent);
  player.querySelector('[data-audio-toggle]').emit('click');
  assert.equal(audio.urls.length, 3); // User can retry after connectivity returns.
  audio.emit('loadedmetadata');
  assert.equal(audio.currentTime, 37);
});
test('next track gets its own renewal allowance and an authenticated fresh URL', async () => {
  const {audio} = await setup();
  audio.emit('error');
  audio.emit('ended');
  assert.equal(audio.src, '/videos/2/media/audio/');
  audio.currentTime = 12;
  audio.emit('error');
  assert.match(audio.src, /\/videos\/2\/media\/audio\/\?renew=/);
  audio.emit('loadedmetadata');
  assert.equal(audio.currentTime, 12);
});
test('filter and visibility changes preserve the playing queue', async () => {
  const {audio, document, setPlaylist} = await setup();
  setPlaylist({label: 'شادی', tracks: [{title: 'new', url: '/videos/3/media/audio/'}]});
  document.emit('playlist-filter-change');
  document.emit('visibilitychange');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(audio.paused, false);
  audio.emit('ended');
  assert.equal(audio.src, '/videos/2/media/audio/');
});
