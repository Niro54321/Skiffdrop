'use strict';
// Skiffdrop phone page: pairs with the PC, sends files in resumable 16 MB pieces,
// lists what the PC shares and swaps text, in six languages. No libraries, nothing leaves the Wi-Fi.

const CHUNK = 16 * 1024 * 1024;
const PARALLEL = 3;
const $ = (id) => document.getElementById(id);

const T = window.SKIFF_I18N;  // from i18n.js

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
function pickLang() {
  const saved = store.get('lang');
  if (saved && T[saved]) return saved;
  for (const l of (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || 'en'])) {
    const code = String(l).toLowerCase().split('-')[0];
    if (T[code]) return code;
  }
  return 'en';
}
let lang = pickLang();

function t(key, ...args) {
  let s = (T[lang] && T[lang][key]) || T.en[key] || key;
  args.forEach((a, i) => { s = s.replace(`{${i}}`, a); });
  return s;
}

function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll('[data-tp]').forEach((el) => { el.placeholder = t(el.dataset.tp); });
  $('lang').value = lang;
  $('langCode').textContent = lang.toUpperCase();
  $('lang').setAttribute('aria-label', t('language'));
  setStatus(state.status);
  if (state.view === 'pair') pairText();
  renderPc();
  jobs.forEach(drawJob);
  drawSum();
}

const state = { view: '', status: 'connecting', pc: '', version: 0, files: [], texts: [], seenFiles: null };

function setStatus(s) {
  state.status = s;
  const el = $('status');
  el.className = 'status ' + (s === 'connected' ? 'on' : s === 'offline' ? 'off' : '');
  // 'found': the PC answered but this phone isn't paired yet, so just name the PC
  $('statusText').textContent = s === 'connected' ? t('connected', state.pc || 'PC')
    : s === 'found' ? (state.pc || 'PC') : t(s);
}

function sizeText(n) {
  // LRI ... PDI: "1.5 MB" stays in that order inside Arabic sentences
  if (n < 1024) return '⁦' + n + ' B⁩';
  const u = ['KB', 'MB', 'GB', 'TB'];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return '⁦' + (n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2)) + ' ' + u[i] + '⁩';
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let toastTimer = 0;
function toast(text) {
  const el = $('toast');
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

async function api(method, path, body) {
  const headers = { 'X-Skiffdrop': '1' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const r = await fetch(path, {
    method, headers, credentials: 'same-origin', cache: 'no-store',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = {};
  try { data = await r.json(); } catch { /* empty body */ }
  return { ok: r.ok, status: r.status, data };
}

// ------------------------------------------------------------------ pairing
let key = '';
let qrCode = '';
(function readKey() {
  const m = location.hash.match(/k=([A-Za-z0-9_-]{8,64})/);
  const c = location.hash.match(/c=(\d{6})/);
  if (m) {
    key = m[1];
    qrCode = c ? c[1] : '';
    try { sessionStorage.setItem('k', key); sessionStorage.setItem('c', qrCode); } catch { /* ignore */ }
    history.replaceState(null, '', location.pathname);  // the key stays out of bookmarks and history
  } else {
    try { key = sessionStorage.getItem('k') || ''; qrCode = sessionStorage.getItem('c') || ''; } catch { key = ''; }
  }
})();

function deviceInfo() {
  const ua = navigator.userAgent;
  let kind = 'other', name = 'Device';
  if (/iPhone|iPod/.test(ua)) { kind = 'ios'; name = 'iPhone'; }
  else if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) { kind = 'ios'; name = 'iPad'; }
  else if (/Android/.test(ua)) {
    kind = 'android';
    const m = ua.match(/Android[^;)]*;\s*([^;)]+?)(?:\s+Build\/[^;)]*)?\)/);
    const model = m && m[1].trim();
    name = model && model !== 'K' && !/^(wv|Linux|U)$/.test(model) ? model : 'Android phone';
  } else if (/Windows/.test(ua)) { kind = 'desktop'; name = 'Windows PC'; }
  else if (/Macintosh/.test(ua)) { kind = 'desktop'; name = 'Mac'; }
  else if (/CrOS/.test(ua)) { kind = 'desktop'; name = 'Chromebook'; }
  else if (/Linux/.test(ua)) { kind = 'desktop'; name = 'Linux PC'; }
  const browser = /EdgA?\/|EdgiOS/.test(ua) ? 'Edge' : /SamsungBrowser/.test(ua) ? 'Samsung Internet'
    : /CriOS|Chrome\//.test(ua) ? 'Chrome' : /FxiOS|Firefox/.test(ua) ? 'Firefox' : /Safari/.test(ua) ? 'Safari' : '';
  return { kind, name: browser ? `${name} · ${browser}` : name };
}

let pinNeeded = false;
function pairText() {
  $('pairMsg').textContent = key ? t('pairKey') : t('pairHelp');
}

function showPair(me) {
  state.view = 'pair';
  pinNeeded = !!(me && me.pin);
  $('home').hidden = true;
  $('pair').hidden = false;
  // From the QR code: the code is already filled in, one tap on Connect is all that's left.
  $('codeRow').hidden = false;
  if (qrCode) $('code').value = qrCode;
  $('pinRow').hidden = !pinNeeded;
  $('pairErr').hidden = true;
  $('waiting').hidden = true;
  $('pairForm').hidden = false;
  pairText();
  if (pinNeeded) $('pin').focus();
  else if (!key) $('code').focus();
}

function pairError(msg) {
  $('waiting').hidden = true;
  $('pairForm').hidden = false;
  $('pairErr').textContent = msg;
  $('pairErr').hidden = false;
}

let pairing = false;
async function pair() {
  if (pairing) return;
  pairing = true;
  try {
    const code = $('code').value.replace(/\D/g, '');
    const info = deviceInfo();
    $('pairErr').hidden = true;
    const r = await api('POST', '/api/pair', { key, code, pin: $('pin').value, name: info.name, kind: info.kind });
    if (!r.ok) {
      if (r.data.error === 'pin') return pairError(t('badPin'));
      if (r.data.error === 'locked') return pairError(t('locked'));
      if (key) {  // an old QR code: fall back to typing the code shown on the PC now
        key = '';
        qrCode = '';
        $('code').value = '';
        try { sessionStorage.removeItem('k'); sessionStorage.removeItem('c'); } catch { /* ignore */ }
        pairText();
      }
      return pairError(t('badCode'));
    }
    $('pairForm').hidden = true;
    $('waiting').hidden = false;
    for (;;) {
      const w = await api('GET', '/api/pair/' + encodeURIComponent(r.data.req));
      if (w.data.status === 'approved') { showHome(); return; }
      if (w.data.status === 'denied') return pairError(t('denied'));
      if (w.data.status === 'expired') return pairError(t('expired'));
    }
  } catch {
    pairError(t('offline'));
  } finally {
    pairing = false;
  }
}

// ------------------------------------------------------------------ home
function showHome() {
  state.view = 'home';
  $('pair').hidden = true;
  $('home').hidden = false;
  try { sessionStorage.removeItem('k'); sessionStorage.removeItem('c'); } catch { /* ignore */ }
  key = '';
  qrCode = '';
  poll();
}

let polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  let failures = 0;
  while (state.view === 'home') {
    try {
      const r = await fetch('/api/events?since=' + state.version, { cache: 'no-store', credentials: 'same-origin' });
      if (r.status === 401) { polling = false; return boot(); }
      const d = await r.json();
      failures = 0;
      state.pc = d.pc;
      setStatus('connected');
      if (d.v !== state.version) {
        state.version = d.v;
        const before = state.seenFiles;
        state.files = d.files;
        state.texts = d.texts;
        state.seenFiles = new Set(d.files.map((f) => f.id).concat(d.texts.map((x) => x.id)));
        if (before && [...state.seenFiles].some((id) => !before.has(id))) {
          toast(t('newFromPc'));
          if (navigator.vibrate) navigator.vibrate(60);
        }
        renderPc();
      }
    } catch {
      failures++;
      setStatus(failures > 1 ? 'offline' : 'connecting');
      await sleep(Math.min(5000, 1000 * failures));
    }
  }
  polling = false;
}

function fileUrl(f, extra) {
  return `/api/file/${f.id}/${encodeURIComponent(f.name)}${extra ? '?' + extra : ''}`;
}

function ext(name) {
  const m = name.match(/\.([A-Za-z0-9]{1,5})$/);
  return m ? m[1] : 'file';
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function renderPc() {
  const list = $('incoming');
  list.textContent = '';
  for (const f of state.files) {
    const li = el('li', 'item');
    const thumb = el('button', 'thumb');
    thumb.type = 'button';
    thumb.appendChild(el('span', '', ext(f.name)));
    if (f.type.startsWith('image/')) {
      const img = new Image();
      img.alt = '';
      img.loading = 'lazy';  // only loads once it is in the page and scrolled near
      img.onload = () => thumb.classList.add('pic');
      img.src = fileUrl(f, 'thumb=1');
      thumb.appendChild(img);
    }
    thumb.onclick = () => view(f);
    const meta = el('div', 'meta');
    const name = el('span', 'name', f.rel || f.name);
    name.onclick = () => view(f);
    meta.append(name, el('span', 'sub', sizeText(f.size)));
    const save = el('a', 'chip', t('save'));
    save.href = fileUrl(f, 'dl=1');
    save.setAttribute('download', f.name);
    li.append(thumb, meta, save);
    list.appendChild(li);
  }
  const texts = $('texts');
  texts.textContent = '';
  for (const m of [...state.texts].reverse()) {
    const li = el('li', 'item msg');
    li.appendChild(el('div', 'body', m.text));
    const acts = el('div', 'acts');
    const copy = el('button', 'chip', t('copy'));
    copy.type = 'button';
    copy.onclick = () => copyText(m.text);
    acts.appendChild(copy);
    const url = m.text.trim();
    if (/^https?:\/\/\S+$/i.test(url)) {
      const open = el('a', 'chip', t('open'));
      open.href = url;
      open.target = '_blank';
      open.rel = 'noopener noreferrer';
      acts.appendChild(open);
    }
    li.appendChild(acts);
    texts.appendChild(li);
  }
  const zip = $('zipAll');
  zip.hidden = state.files.length < 2;
  zip.href = '/api/zip/Skiffdrop.zip?dl=1';
  $('emptyPc').hidden = state.files.length + state.texts.length > 0;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);  // only on https or localhost
  } catch {
    const ta = el('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    try { document.execCommand('copy'); } catch { /* nothing else to try */ }
    ta.remove();
  }
  toast(t('copied'));
}

function view(f) {
  const body = $('viewerBody');
  body.textContent = '';
  $('viewerName').textContent = f.name;
  $('viewerSave').href = fileUrl(f, 'dl=1');
  $('viewerSave').setAttribute('download', f.name);
  let hint = t('fileHint');
  if (f.type.startsWith('image/')) {
    const img = new Image();
    img.src = fileUrl(f, 'inline=1');
    img.alt = f.name;
    body.appendChild(img);
    hint = t('holdPhoto');
  } else if (f.type.startsWith('video/') || f.type.startsWith('audio/')) {
    const v = document.createElement(f.type.startsWith('video/') ? 'video' : 'audio');
    v.controls = true;
    v.playsInline = true;
    v.preload = 'metadata';
    v.src = fileUrl(f, 'inline=1');
    body.appendChild(v);
    hint = t('videoHint');
  }
  $('viewerHint').textContent = hint;
  $('viewer').hidden = false;
}

function closeViewer() {
  $('viewer').hidden = true;
  $('viewerBody').textContent = '';  // stops a playing video
}

// ------------------------------------------------------------------ uploads
const jobs = [];
let samples = [];

class Job {
  constructor(file) {
    this.file = file;
    this.id = '';
    this.sent = 0;
    this.inflight = 0;
    this.state = 'wait';      // wait / run / retry / done / failed / cancelled
    this.note = '';
    this.xhr = null;
    this.li = null;
  }
  get done() { return Math.min(this.file.size, this.sent + this.inflight); }
}

function addFiles(list) {
  for (const f of list) {
    const job = new Job(f);
    jobs.push(job);
    drawJob(job);
  }
  drawSum();
  pump();
}

function pump() {
  let running = jobs.filter((j) => j.state === 'run' || j.state === 'retry').length;
  for (const j of jobs) {
    if (running >= PARALLEL) break;
    if (j.state === 'wait') {
      running++;
      run(j);
    }
  }
}

async function run(job) {
  job.state = 'run';
  drawJob(job);
  try {
    await upload(job);
    if (job.state !== 'cancelled') job.state = 'done';
  } catch (e) {
    if (job.state !== 'cancelled') {
      job.state = 'failed';
      job.note = e && e.read ? t('errRead') : e && e.data && e.data.error === 'disk_full' ? t('diskFull')
        : e && e.status === 404 ? t('errGone') : t('errNet');
    }
  }
  job.inflight = 0;
  drawJob(job);
  drawSum();
  pump();
}

async function upload(job) {
  const f = job.file;
  const s = await api('POST', '/api/upload', { name: f.name, size: f.size, modified: f.lastModified || 0 });
  if (!s.ok) throw s;
  job.id = s.data.id;
  job.sent = s.data.received || 0;
  if (s.data.saved) job.saved = s.data.saved;
  let tries = 0;
  while (job.sent < f.size && job.state !== 'cancelled') {
    const end = Math.min(f.size, job.sent + CHUNK);
    try {
      const res = await put(job, job.sent, f.slice(job.sent, end));
      job.sent = res.received;
      if (res.saved) job.saved = res.saved;
      if (job.state === 'retry') { job.state = 'run'; drawJob(job); }
      tries = 0;
    } catch (e) {
      job.inflight = 0;
      if (job.state === 'cancelled') return;
      if (e.status === 409 && e.data && typeof e.data.received === 'number') { job.sent = e.data.received; continue; }
      if (e.status === 401 || e.status === 404 || e.status === 413) throw e;
      try {  // the network, or the file itself? (iOS can take a picked file away)
        await f.slice(job.sent, job.sent + 1).arrayBuffer();
      } catch {
        throw { read: true };
      }
      if (++tries > 40) throw e;
      job.state = 'retry';
      drawJob(job);
      await sleep(Math.min(8000, 400 * 2 ** Math.min(tries, 5)));
      try {
        const st = await api('GET', '/api/upload/' + job.id);
        if (st.status === 404) throw st;
        if (st.ok) job.sent = st.data.received;
      } catch (e2) {
        if (e2 && e2.status === 404) throw e2;
      }
    }
  }
}

function put(job, offset, blob) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    job.xhr = x;
    x.open('PUT', `/api/upload/${job.id}?offset=${offset}`);
    x.setRequestHeader('X-Skiffdrop', '1');
    x.setRequestHeader('Content-Type', 'application/octet-stream');
    x.timeout = 0;
    x.upload.onprogress = (e) => { job.inflight = e.loaded; tick(); };
    x.onload = () => {
      job.xhr = null;
      job.inflight = 0;
      let d = {};
      try { d = JSON.parse(x.responseText); } catch { /* not json */ }
      if (x.status === 200) resolve(d); else reject({ status: x.status, data: d });
    };
    x.onerror = () => { job.xhr = null; reject({ status: 0 }); };
    x.onabort = () => { job.xhr = null; reject({ status: -1 }); };
    x.send(blob);
  });
}

function cancel(job) {
  if (job.state === 'done' || job.state === 'failed' || job.state === 'cancelled') return;
  job.state = 'cancelled';
  if (job.xhr) job.xhr.abort();
  if (job.id) api('DELETE', '/api/upload/' + job.id).catch(() => {});
  drawJob(job);
  drawSum();
  pump();
}

function speed() {
  if (samples.length < 2) return 0;
  const a = samples[0], b = samples[samples.length - 1];
  return b.t > a.t ? (b.n - a.n) / ((b.t - a.t) / 1000) : 0;
}

let tickTimer = 0;
function tick() {
  if (tickTimer) return;
  tickTimer = setTimeout(() => {
    tickTimer = 0;
    const total = jobs.reduce((s, j) => s + (j.state === 'cancelled' ? 0 : j.done), 0);
    const now = performance.now();
    samples.push({ t: now, n: total });
    samples = samples.filter((s) => now - s.t < 3000);
    jobs.forEach((j) => { if (j.state === 'run' || j.state === 'retry') drawJob(j); });
    drawSum();
  }, 250);
}

function drawJob(job) {
  if (!job.li) {
    job.li = el('li', 'item');
    const meta = el('div', 'meta');
    job.nameEl = el('span', 'name', job.file.name);
    job.barEl = el('div', 'bar');
    job.barEl.appendChild(el('i'));
    job.subEl = el('span', 'sub');
    meta.append(job.nameEl, job.barEl, job.subEl);
    job.xEl = el('button', 'x', '✕');
    job.xEl.type = 'button';
    job.xEl.setAttribute('aria-label', 'Cancel');
    job.xEl.onclick = () => cancel(job);
    job.li.append(meta, job.xEl);
    $('queue').prepend(job.li);
  }
  const f = job.file;
  const pct = f.size ? (job.done / f.size) * 100 : (job.state === 'done' ? 100 : 0);
  job.barEl.firstChild.style.width = pct.toFixed(1) + '%';
  job.li.classList.toggle('done', job.state === 'done');
  job.subEl.className = 'sub' + (job.state === 'done' ? ' ok' : job.state === 'failed' ? ' bad' : '');
  job.xEl.hidden = !(job.state === 'wait' || job.state === 'run' || job.state === 'retry');
  job.subEl.textContent =
    job.state === 'wait' ? `${t('wait')} · ${sizeText(f.size)}`
      : job.state === 'run' ? t('of', sizeText(job.done), sizeText(f.size))
        : job.state === 'retry' ? t('retrying')
          : job.state === 'done' ? t('saved', job.saved || f.name)
            : job.state === 'failed' ? t('failed', job.note) : t('cancelled');
}

function drawSum() {
  const live = jobs.filter((j) => j.state !== 'cancelled');
  $('queueHead').hidden = jobs.length === 0;
  const done = live.filter((j) => j.state === 'done').length;
  const busy = jobs.some((j) => j.state === 'run' || j.state === 'retry' || j.state === 'wait');
  const sp = busy ? speed() : 0;
  $('queueSum').textContent = t('sum', done, live.length) + (sp > 0 ? ` · ${sizeText(sp)}/s` : '');
  $('clearDone').hidden = busy;
  if (!busy) samples = [];
}

function clearDone() {
  for (let i = jobs.length - 1; i >= 0; i--) {
    const j = jobs[i];
    if (j.state === 'done' || j.state === 'failed' || j.state === 'cancelled') {
      j.li && j.li.remove();
      jobs.splice(i, 1);
    }
  }
  drawSum();
}

// ------------------------------------------------------------------ start
async function boot() {
  setStatus('connecting');
  for (let i = 0; ; i++) {
    try {
      const me = await api('GET', '/api/me');
      state.pc = me.data.pc || '';
      setStatus(me.data.paired ? 'connected' : 'connecting');
      if (me.data.paired) showHome(); else { setStatus('found'); showPair(me.data); }
      return;
    } catch {
      setStatus('offline');
      await sleep(Math.min(5000, 1000 * (i + 1)));
    }
  }
}

function wire() {
  for (const code of Object.keys(T)) {
    const o = document.createElement('option');
    o.value = code;
    o.textContent = T[code]._name;
    $('lang').appendChild(o);
  }
  $('lang').onchange = () => { lang = $('lang').value; store.set('lang', lang); applyLang(); };
  $('pairForm').onsubmit = (e) => { e.preventDefault(); pair(); };
  $('code').oninput = () => {
    const v = $('code').value.replace(/\D/g, '').slice(0, 6);
    $('code').value = v;
    if (v.length === 6 && !pinNeeded) pair();
  };
  for (const id of ['media', 'files']) {
    $(id).onchange = (e) => { addFiles([...e.target.files]); e.target.value = ''; };
  }
  $('clearDone').onclick = clearDone;
  $('sendText').onclick = async () => {
    const text = $('text').value;
    if (!text.trim()) return;
    try {
      const r = await api('POST', '/api/text', { text });
      if (r.ok) { $('text').value = ''; toast(t('textSent')); } else toast(t('errNet'));
    } catch { toast(t('errNet')); }
  };
  $('bye').onclick = async () => {
    if (!confirm(t('forgetAsk'))) return;
    try { await api('POST', '/api/bye'); } catch { /* offline: the cookie stays until the PC forgets it */ }
    state.view = '';
    location.reload();
  };
  $('viewerClose').onclick = closeViewer;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeViewer(); });
  // Dropping files works too when the page is opened on another computer.
  document.addEventListener('dragover', (e) => { if (state.view === 'home') { e.preventDefault(); document.body.classList.add('drag'); } });
  document.addEventListener('dragleave', () => document.body.classList.remove('drag'));
  document.addEventListener('drop', (e) => {
    document.body.classList.remove('drag');
    if (state.view !== 'home' || !e.dataTransfer || !e.dataTransfer.files.length) return;
    e.preventDefault();
    addFiles([...e.dataTransfer.files]);
  });
  window.addEventListener('beforeunload', (e) => {
    if (jobs.some((j) => j.state === 'run' || j.state === 'retry' || j.state === 'wait')) {
      e.preventDefault();
      e.returnValue = t('leave');
    }
  });
  if (navigator.wakeLock) {  // https only; harmless elsewhere
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && jobs.some((j) => j.state === 'run')) {
        navigator.wakeLock.request('screen').catch(() => {});
      }
    });
  }
}

window.skiffdrop = { addFiles, jobs, state };  // used by the automated tests
wire();
applyLang();
boot();
