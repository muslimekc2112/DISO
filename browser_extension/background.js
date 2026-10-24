// Background script: context menu entries and (optionally) taking over the browser's downloads.
// It only ever talks to the DISO app on 127.0.0.1, and - when DISO is closed - to its native host,
// which starts DISO (app/native_host.py). (lib.js is loaded before this file.)
"use strict";

const api = typeof browser !== "undefined" ? browser : chrome;
const bypass = new Set();   // links we gave back to the browser because the app could not take them

async function getOptions() {
  const stored = await api.storage.local.get(HI.DEFAULTS);
  return Object.assign({}, HI.DEFAULTS, stored);
}

// ------------------------------------------------------------------------ language
// The extension speaks the language chosen in its settings; "app" (the default) follows DISO: the
// language DISO told last (appLang, kept for when it is closed), else the browser's.
let menusLanguage = null;
async function applyLanguage(opts) {
  const code = HI.setLanguage(HI.pickLanguage(opts.lang, opts.appLang));
  if (code !== menusLanguage) createMenus();
  return code;
}

// The app answers /ping with {"app": "DISO", "language": "tr" | "en", ...}. null = not running / something else.
async function ping(port) {
  try {
    const r = await fetch(HI.appBase(port) + "/ping", { cache: "no-store" });
    const data = await r.json();
    if (!(data && data.app === HI.APP_ID)) return null;
    if ((data.language === "tr" || data.language === "en")) {
      const opts = await getOptions();
      if (opts.appLang !== data.language) await api.storage.local.set({ appLang: data.language });
      await applyLanguage(Object.assign(opts, { appLang: data.language }));
    }
    return data;
  } catch (e) {
    return null;
  }
}

// DISO's answer to /ping; when it is closed (and the user allows it) the native host starts it first.
let launching = null;       // one start at a time, however many links arrive meanwhile
async function ensureApp(opts) {
  const running = await ping(opts.port);
  if (running || !opts.launchApp || !(api.runtime && api.runtime.sendNativeMessage)) return running;
  if (!launching) {
    launching = (async () => {
      try {
        const r = await api.runtime.sendNativeMessage(HI.HOST, { type: "launch", port: Number(opts.port) });
        return !!(r && r.ok);
      } catch (e) {
        return false;          // no native host registered (DISO never ran), or it failed
      }
    })().finally(() => { launching = null; });
  }
  if (!(await launching)) return null;
  return ping((await getOptions()).port);
}

async function cookiesFor(url) {
  try {
    return HI.cookieHeader(await api.cookies.getAll({ url }));
  } catch (e) {
    return "";
  }
}

// Send links to the app. For a single link the browser's session (cookies, referer) goes along,
// so downloads that need a login work. Resolves with the app's answer, rejects if it fails.
async function sendToApp(urls, { referer = "", kind = null } = {}) {
  await ensureApp(await getOptions());
  const opts = await getOptions();                 // read again: the settings may have changed meanwhile
  const cookies = urls.length === 1 ? await cookiesFor(urls[0]) : "";
  const payload = HI.buildPayload({ urls, referer, userAgent: navigator.userAgent, cookies, kind });
  const r = await fetch(HI.appBase(opts.port) + "/add", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-HI-Client": "extension" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const why = (await r.json().catch(() => ({}))).error || r.status;
    throw new Error(why === "disabled" ? HI.t("bridgeOff") : HI.t("refused", [why]));
  }
  return r.json();
}

// POST a ready payload (found videos, a page with its streams) to DISO, starting it when it is closed.
async function postToApp(payload) {
  await ensureApp(await getOptions());
  const opts = await getOptions();
  const r = await fetch(HI.appBase(opts.port) + "/add", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-HI-Client": "extension" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const why = (await r.json().catch(() => ({}))).error || r.status;
    throw new Error(why === "disabled" ? HI.t("bridgeOff") : HI.t("refused", [why]));
  }
  return r.json();
}

async function flash(text, ok) {
  const opts = await getOptions();
  if (!opts.badge) return;
  try {
    await api.action.setBadgeBackgroundColor({ color: ok ? "#2e9e5b" : "#b23b3b" });
    await api.action.setBadgeText({ text: text });
    setTimeout(() => api.action.setBadgeText({ text: "" }), 2500);
  } catch (e) { /* no toolbar button in this browser */ }
}

// Links with what each one is (HI.linkKind): files go as "file", pages as "auto", one request per kind.
async function sendLinks(urls, extra) {
  const groups = new Map();
  urls.forEach((u) => {
    const kind = HI.linkKind(u);
    groups.set(kind, (groups.get(kind) || []).concat([u]));
  });
  const total = { added: 0, duplicates: 0 };
  for (const [kind, group] of groups) {
    const r = await sendToApp(group, Object.assign({}, extra, { kind }));
    total.added += r.added || 0;
    total.duplicates += r.duplicates || 0;
  }
  return total;
}

async function sendAndShow(urls, extra) {
  try {
    // a kind given by the user (MP4 / MP3 of a page) is kept; otherwise each link says what it is
    const result = extra && extra.payload ? await postToApp(extra.payload)
      : extra && extra.kind ? await sendToApp(urls, extra) : await sendLinks(urls, extra || {});
    await flash(result.added ? "✓" : "=", true);
    return { ok: true, result, text: HI.describeResult(result) };
  } catch (e) {
    await flash("!", false);
    // a fetch that cannot connect throws a TypeError in every browser (the wording differs)
    const unreachable = e && e.name === "TypeError";
    return { ok: false, text: unreachable ? HI.t("unreachableOpen") : String(e && e.message || e) };
  }
}

// Every link of the page in the tab (needs the page itself: a script runs there once).
async function linksOf(tab) {
  try {
    const results = await api.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => Array.from(document.links, (a) => a.href),
    });
    return [].concat(...(results || []).map((r) => r.result || []));
  } catch (e) {
    return [];                 // a page the browser does not let extensions read (its own pages, the store)
  }
}

async function fileLinksOf(tab) {
  const opts = await getOptions();
  return HI.pageFileLinks(await linksOf(tab), opts.extensions);
}

// 🧲 the magnet links and .torrent files of the page
async function torrentLinksOf(tab) {
  return HI.pageTorrentLinks(await linksOf(tab));
}

// ------------------------------------------------------------------------ context menu
function createMenus() {
  menusLanguage = HI.currentLanguage();
  api.contextMenus.removeAll(() => {
    api.contextMenus.create({ id: "hi-link", title: HI.t("menuLink"), contexts: ["link"] });
    api.contextMenus.create({ id: "hi-media", title: HI.t("menuLink"), contexts: ["video", "audio", "image"] });
    api.contextMenus.create({ id: "hi-page-video", title: HI.t("menuPageVideo"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-page-audio", title: HI.t("menuPageAudio"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-found", title: HI.t("menuFound"), contexts: ["page", "video", "audio"] });
    api.contextMenus.create({ id: "hi-series", title: HI.t("menuSeries"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-all-links", title: HI.t("menuAllLinks"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-torrents", title: HI.t("menuTorrents"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-selection", title: HI.t("menuSelection"), contexts: ["selection"] });
  });
}
api.runtime.onInstalled.addListener(createMenus);
// the menus (and every text) in the right language from the start, and again when the setting changes
getOptions().then(applyLanguage);
if (api.storage.onChanged) {
  api.storage.onChanged.addListener((changes) => {
    if (changes.lang || changes.appLang) getOptions().then(applyLanguage);
  });
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  const referer = (tab && tab.url) || info.pageUrl || "";
  if (info.menuItemId === "hi-link") return sendAndShow([info.linkUrl], { referer });
  if (info.menuItemId === "hi-media") return sendAndShow([info.srcUrl], { referer });
  if (info.menuItemId === "hi-page-video") return sendPage(tab, info.pageUrl || referer, "video");
  if (info.menuItemId === "hi-page-audio") return sendPage(tab, info.pageUrl || referer, "audio");
  if (info.menuItemId === "hi-series") {
    const list = tab ? await episodesOf(tab) : { episodes: [] };
    if (!list.episodes.length) { await flash("0", false); return { ok: false, text: HI.t("noEpisodes") }; }
    const opts = await getOptions();
    return startSeries(tab, list.episodes.map((e) => e.url), "video", opts.quality, opts.withSubs);
  }
  if (info.menuItemId === "hi-found") {
    const found = tab ? await foundOn(tab.id) : null;
    if (!found || !found.media.length) { await flash("0", false); return { ok: false, text: HI.t("foundNone") }; }
    const opts = await getOptions();
    return sendFound(tab.id, HI.rankMedia(found.media).slice(0, 1).map((e) => e.url), "video", opts.quality, opts.withSubs);
  }
  if (info.menuItemId === "hi-all-links") {
    const urls = tab ? await fileLinksOf(tab) : [];
    if (!urls.length) { await flash("0", false); return { ok: false, text: HI.t("noFileLinks") }; }
    return sendAndShow(urls, { referer });
  }
  if (info.menuItemId === "hi-torrents") {
    const urls = tab ? await torrentLinksOf(tab) : [];
    if (!urls.length) { await flash("0", false); return { ok: false, text: HI.t("noTorrents") }; }
    return sendAndShow(urls, { referer });
  }
  if (info.menuItemId === "hi-selection") {
    const urls = HI.extractUrls(info.selectionText);
    if (!urls.length) return flash("?", false);
    return sendAndShow(urls, { referer });
  }
});

// -------------------------------------------------------------- take over browser downloads
// When the extension got ready in this browser session. Downloads that started before it belong to
// the history the browser reports again and again (it starts, the extension is added or updated):
// never taken. Kept in storage.session (emptied when the browser starts and when the extension is
// added, reloaded or updated), so the service worker going to sleep and waking up changes nothing.
let readyPromise = null;
function readySince() {
  if (!readyPromise) {
    readyPromise = (async () => {
      const session = api.storage.session;
      try {
        const { readyAt } = session ? await session.get("readyAt") : {};
        if (readyAt > 0) return readyAt;
      } catch (e) { /* no session storage: the moment this script started */ }
      const now = Date.now();
      try { if (session) await session.set({ readyAt: now }); } catch (e) { /* kept in memory then */ }
      return now;
    })();
  }
  return readyPromise;
}
readySince();
if (api.runtime.onStartup) api.runtime.onStartup.addListener(readySince);   // wakes the extension with the browser
api.runtime.onInstalled.addListener(readySince);

// Is the browser still downloading it? (A small file may be done before DISO has answered.)
async function stillDownloading(id) {
  try {
    const [now] = await api.downloads.search({ id });
    return !!now && now.state === "in_progress";
  } catch (e) {
    return true;
  }
}

api.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (bypass.has(url)) { bypass.delete(url); return; }
  const opts = await getOptions();
  if (!HI.shouldIntercept(item, opts, Date.now(), await readySince())) return;
  let app = await ping(opts.port);
  if (!app && opts.launchApp) {                   // DISO is closed: hold the download while it starts
    try { await api.downloads.pause(item.id); } catch (e) { /* already finished, or cannot pause */ }
    app = await ensureApp(opts);
    if (!app || !app.add) {
      try { await api.downloads.resume(item.id); } catch (e) { /* nothing more to do */ }
      return;
    }
  }
  if (!app || !app.add) return;                    // the app is closed (or adding is off): the browser keeps it
  if (!(await stillDownloading(item.id))) return;  // a small file the browser has already finished: keep it, once
  try {
    await api.downloads.cancel(item.id);
    await api.downloads.erase({ id: item.id });
    // the browser was downloading it: it is a file, never something to turn into MP4 / MP3
    const result = await sendToApp([url], { referer: item.referrer || "", kind: "file" });
    await flash(result.added ? "✓" : "=", true);
  } catch (e) {                                    // could not hand it over: give it back to the browser
    bypass.add(url);
    try { await api.downloads.download({ url }); } catch (e2) { /* nothing more to do */ }
    await flash("!", false);
  }
});

// ------------------------------------------------------------------- popup / options pages
async function appStatus(port) {
  try {
    const r = await fetch(HI.appBase(port) + "/status", { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;
  }
}

async function openApp() {
  const opts = await getOptions();
  const app = await ensureApp(Object.assign({}, opts, { launchApp: true }));   // asked for by hand: always
  if (!app) return { ok: false, text: HI.t("openFailed") };
  try {
    await fetch(HI.appBase((await getOptions()).port) + "/show", { method: "POST", headers: { "X-HI-Client": "extension" } });
  } catch (e) { /* it is open anyway */ }
  return { ok: true, app };
}

// ------------------------------------------------------------- 🎞 videos the pages play
// Every request a tab makes is looked at (only looked at: nothing is changed or blocked). Playlists of streams
// (.m3u8 / .mpd), whole video / sound files and subtitles are remembered for the tab, with the headers the page's
// player sent (Referer, Origin, cookies): many servers only answer the player. The toolbar button counts them.
const found = new Map();          // tabId -> {page, title, media: [...], subs: [...]}
const sentHeaders = new Map();    // requestId -> the request's headers, until its answer comes
const recentHeaders = new Map();  // url -> the headers of a recent request that looked like nothing (see "stream")
const MAX_PENDING = 600;
const TYPES = ["media", "xmlhttprequest", "other", "object"];

async function foundOn(tabId) {
  if (found.has(tabId)) return found.get(tabId);
  try {                            // the service worker slept: what it had found is in the session storage
    const key = "found:" + tabId;
    const saved = api.storage.session ? (await api.storage.session.get(key))[key] : null;
    if (saved && Array.isArray(saved.media)) { found.set(tabId, saved); return saved; }
  } catch (e) { /* nothing kept */ }
  return null;
}

let keepTimer = null;
function keepFound() {             // written down now and then, not on every request
  if (keepTimer || !api.storage.session) return;
  keepTimer = setTimeout(async () => {
    keepTimer = null;
    const all = {};
    for (const [tabId, f] of found) all["found:" + tabId] = f;
    try { await api.storage.session.set(all); } catch (e) { /* too big or no session storage: kept in memory */ }
  }, 800);
}

async function showCount(tabId) {
  const f = found.get(tabId);
  const opts = await getOptions();
  if (!opts.sniff || !opts.badge) return;
  try {
    await api.action.setBadgeBackgroundColor({ tabId, color: "#7b3fa0" });
    await api.action.setBadgeText({ tabId, text: HI.badgeCount(f ? f.media.length : 0) });
  } catch (e) { /* the tab is gone */ }
}

function forget(tabId) {
  found.delete(tabId);
  try { if (api.storage.session) api.storage.session.remove("found:" + tabId); } catch (e) { /* nothing kept */ }
  try { api.action.setBadgeText({ tabId, text: "" }); } catch (e) { /* the tab is gone */ }
}

function onSendHeaders(details) {
  if (details.tabId < 0) return;
  if (sentHeaders.size > MAX_PENDING) sentHeaders.delete(sentHeaders.keys().next().value);
  sentHeaders.set(details.requestId, details.requestHeaders || []);
}

async function onResponse(details) {
  const sent = sentHeaders.get(details.requestId) || [];
  sentHeaders.delete(details.requestId);
  if (details.tabId < 0 || (details.statusCode && details.statusCode >= 400)) return;
  const headers = details.responseHeaders || [];
  const kind = HI.mediaKind(details.url, HI.headerValue(headers, "content-type"), HI.responseSize(headers));
  if (!kind) {                                     // may still be a playlist with another name: sniff.js will say
    if (recentHeaders.size > MAX_PENDING) recentHeaders.delete(recentHeaders.keys().next().value);
    recentHeaders.set(details.url, { sent, documentUrl: details.documentUrl || details.initiator || "" });
    return;
  }
  const opts = await getOptions();
  if (!opts.sniff) return;
  let f = await foundOn(details.tabId);
  if (!f) {
    f = { page: "", title: "", media: [], subs: [] };
    found.set(details.tabId, f);
  }
  const entry = {
    url: details.url, kind, size: HI.responseSize(headers), time: Date.now(),
    referer: HI.headerValue(sent, "referer") || details.documentUrl || details.initiator || "",
    origin: HI.headerValue(sent, "origin"), userAgent: HI.headerValue(sent, "user-agent"),
    cookies: HI.headerValue(sent, "cookie"),
  };
  if (kind === "subtitle") {
    HI.addFound(f.subs, { url: entry.url, lang: HI.subtitleLanguage(entry.url), ext: HI.fileExtension(entry.url) === "srt" ? "srt" : "vtt" }, 20);
  } else if (HI.addFound(f.media, entry, 40)) {
    try {
      const tab = await api.tabs.get(details.tabId);
      f.page = tab.url || f.page;
      f.title = tab.title || f.title;
    } catch (e) { /* the tab is gone */ }
    showCount(details.tabId);
  }
  keepFound();
}

// 🎞 sniff.js found a playlist hidden behind another name ("#EXTM3U" at its start): it is an HLS stream
async function hiddenStream(url, sender) {
  const tabId = sender && sender.tab ? sender.tab.id : -1;
  if (tabId < 0 || !HI.isHttpUrl(url)) return { ok: false };
  const opts = await getOptions();
  if (!opts.sniff) return { ok: false };
  const seen = recentHeaders.get(url) || { sent: [], documentUrl: "" };
  let f = await foundOn(tabId);
  if (!f) {
    f = { page: "", title: "", media: [], subs: [] };
    found.set(tabId, f);
  }
  const entry = { url, kind: "hls", size: 0, time: Date.now(),
                  referer: HI.headerValue(seen.sent, "referer") || (sender.url || seen.documentUrl || ""),
                  origin: HI.headerValue(seen.sent, "origin"), userAgent: HI.headerValue(seen.sent, "user-agent"),
                  cookies: HI.headerValue(seen.sent, "cookie") };
  if (HI.addFound(f.media, entry, 40)) {
    try {
      const tab = await api.tabs.get(tabId);
      f.page = tab.url || f.page;
      f.title = tab.title || f.title;
    } catch (e) { /* the tab is gone */ }
    showCount(tabId);
    keepFound();
  }
  return { ok: true };
}

if (api.webRequest && api.webRequest.onSendHeaders) {
  const filter = { urls: ["<all_urls>"], types: TYPES };
  const extra = ["requestHeaders"];
  // Chrome only gives Referer / Cookie with "extraHeaders"; Firefox gives them anyway (and does not know it)
  if (api.webRequest.OnSendHeadersOptions && api.webRequest.OnSendHeadersOptions.EXTRA_HEADERS) extra.push("extraHeaders");
  try {
    api.webRequest.onSendHeaders.addListener(onSendHeaders, filter, extra);
    api.webRequest.onResponseStarted.addListener(onResponse, filter, ["responseHeaders"]);
    if (api.webRequest.onErrorOccurred) api.webRequest.onErrorOccurred.addListener((d) => sentHeaders.delete(d.requestId), filter);
  } catch (e) { /* a browser without it: only links can be sent */ }
}
if (api.tabs && api.tabs.onUpdated) {
  api.tabs.onUpdated.addListener((tabId, change) => {
    if (change.status === "loading" && change.url) forget(tabId);         // another page in the tab
  });
}
if (api.tabs && api.tabs.onRemoved) api.tabs.onRemoved.addListener((tabId) => forget(tabId));

// ------------------------------------------------------------------ 📺 series mode
// The episodes of a series are opened one by one in a small, muted window of their own; each one's player is
// started, the stream it plays is caught (as above) and sent to DISO as "<series> - S01 Episode 02" (in the
// extension's language), into a folder named after the series. An episode whose video does not show up in time goes to DISO as its page (DISO tries).
const SERIES_WAIT = () => Number(globalThis.DISO_SERIES_WAIT) || 40000;    // ms for an episode's video to show up
const SETTLE_MS = () => Number(globalThis.DISO_SERIES_SETTLE) || 1500;      // ... and for its other qualities
let series = { running: false };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// every link of the page with its words (the episode lists say "Episode 12" in the text, not in the address)
async function linksWithText(tab) {
  try {
    const results = await api.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => Array.from(document.links, (a) => ({ href: a.href, text: (a.textContent || a.title || "").trim().slice(0, 120) })),
    });
    return [].concat(...(results || []).map((r) => r.result || []));
  } catch (e) {
    return [];
  }
}

async function episodesOf(tab) {
  const episodes = HI.episodeLinks(await linksWithText(tab), tab.url || "");
  return { episodes, series: HI.seriesName(tab.title || "") };
}

// runs in the episode's page (every frame): start the players, muted (a muted video may start by itself)
function startPlayers() {
  document.querySelectorAll("video, audio").forEach((v) => {
    try { v.muted = true; const p = v.play(); if (p && p.catch) p.catch(() => {}); } catch (e) { /* not this one */ }
  });
  const buttons = [".vjs-big-play-button", ".jw-icon-display", ".jw-display-icon-container", ".plyr__control--overlaid",
                   ".ytp-large-play-button", "[class*='play-button']", "[class*='playButton']", "[class*='btn-play']",
                   "button[aria-label*='Play' i]", "button[title*='Play' i]", "button[aria-label*='Oynat' i]"];
  for (const sel of buttons) {
    const el = document.querySelector(sel);
    if (el) { try { el.click(); } catch (e) { /* not clickable */ } break; }
  }
}

async function waitForMedia(tabId, job) {
  const end = Date.now() + SERIES_WAIT();
  let poked = 0;
  while (Date.now() < end && !job.stop) {
    const f = await foundOn(tabId);
    if (f && f.media.length) {
      await sleep(SETTLE_MS());                                  // the master playlist / other qualities come along
      return HI.rankMedia(((await foundOn(tabId)) || f).media)[0];
    }
    if (Date.now() - poked > 3000) {
      poked = Date.now();
      try { await api.scripting.executeScript({ target: { tabId, allFrames: true }, func: startPlayers }); } catch (e) { /* loading */ }
    }
    try { await api.tabs.get(tabId); } catch (e) { return null; }   // (also keeps the extension awake)
    await sleep(500);
  }
  return null;
}

async function runSeries(job) {
  let win = null;
  try {
    win = await api.windows.create({ url: "about:blank", type: "popup", width: 560, height: 360, focused: false });
  } catch (e) {
    Object.assign(series, { running: false, error: String(e && e.message || e) });
    return;
  }
  const tabId = win.tabs && win.tabs[0] ? win.tabs[0].id : null;
  job.windowId = win.id;
  try { await api.tabs.update(tabId, { muted: true }); } catch (e) { /* plays silently anyway: muted video */ }
  for (let i = 0; i < job.episodes.length && !job.stop; i++) {
    const ep = job.episodes[i];
    const label = HI.episodeName(ep, job.episodes.length);
    Object.assign(series, { index: i + 1, label });
    forget(tabId);
    try { await api.tabs.update(tabId, { url: ep.url }); } catch (e) { break; }      // the window was closed
    const media = await waitForMedia(tabId, job);
    if (job.stop) break;
    const title = job.name + " - " + label;
    let payload;
    if (media) {
      const f = await foundOn(tabId);
      payload = HI.buildMediaPayload([media], { kind: job.kind, quality: job.quality, title,
        subs: job.withSubs && job.kind !== "audio" && f ? f.subs : [], userAgent: navigator.userAgent });
    } else {
      series.missed += 1;
      payload = HI.buildPayload({ urls: [ep.url], kind: job.kind, userAgent: navigator.userAgent, cookies: await cookiesFor(ep.url) });
      payload.title = title;
      if (job.quality && job.quality !== "En iyi" && job.kind !== "audio") payload.quality = job.quality;
    }
    payload.folder = job.name;
    try {
      await postToApp(payload);
      series.sent += 1;
    } catch (e) {
      series.error = String(e && e.message || e);
    }
  }
  try { if (job.windowId !== undefined) await api.windows.remove(job.windowId); } catch (e) { /* closed by hand */ }
  forget(tabId);
  Object.assign(series, { running: false, stopped: !!job.stop });

}

async function startSeries(tab, urls, kind, quality, withSubs) {
  if (series.running) return { ok: false, text: HI.t("seriesBusy", [series.index, series.total, series.label]) };
  const list = await episodesOf(tab);
  const episodes = list.episodes.filter((e) => urls.includes(e.url));
  if (!episodes.length) return { ok: false, text: HI.t("noEpisodes") };
  const job = { episodes, name: list.series, kind: kind === "audio" ? "audio" : "video", quality, withSubs, stop: false };
  series = { running: true, index: 0, total: episodes.length, label: "", sent: 0, missed: 0, job };
  await api.storage.local.set({ quality: quality || "En iyi", withSubs: !!withSubs });
  runSeries(job);                                              // goes on by itself; the popup asks how far it is
  return { ok: true, text: HI.t("seriesBusy", [1, episodes.length, HI.episodeName(episodes[0], episodes.length)]) };
}

function seriesStatus() {
  const s = series;
  let text = "";
  if (s.running) text = HI.t("seriesBusy", [s.index || 1, s.total, s.label || ""]);
  else if (s.stopped) text = HI.t("seriesStopped");
  else if (s.total) text = s.missed ? HI.t("seriesDone", [s.sent, s.missed]) : HI.t("seriesDoneAll", [s.sent]);
  return { running: !!s.running, index: s.index || 0, total: s.total || 0, sent: s.sent || 0, missed: s.missed || 0, text };
}

// The chosen found videos of a tab (by address) as downloads: MP4 or MP3, in a quality, with the subtitles.
async function sendFound(tabId, urls, kind, quality, withSubs) {
  const f = await foundOn(tabId);
  if (!f) return { ok: false, text: HI.t("foundNone") };
  const chosen = f.media.filter((e) => urls.includes(e.url));
  if (!chosen.length) return { ok: false, text: HI.t("nothingChosen") };
  const opts = await getOptions();
  await api.storage.local.set({ quality: quality || opts.quality, withSubs: !!withSubs });
  const payload = HI.buildMediaPayload(HI.rankMedia(chosen), {
    kind, quality, title: f.title, subs: withSubs && kind !== "audio" ? f.subs : [], userAgent: navigator.userAgent });
  const r = await sendAndShow([], { payload });
  if (r.ok) r.text = HI.t("sentFound", [chosen.length]);
  return r;
}

// "MP4 / MP3 of this page": the page itself, and the streams it played for when DISO cannot read the site.
async function sendPage(tab, pageUrl, kind) {
  const f = tab && tab.id !== undefined ? await foundOn(tab.id) : null;
  const opts = await getOptions();
  const payload = HI.buildPayload({ urls: [pageUrl], kind, userAgent: navigator.userAgent, cookies: await cookiesFor(pageUrl) });
  if (f && f.media.length) {
    payload.alternates = HI.alternatesOf(f.media, navigator.userAgent);
    payload.title = (tab && tab.title) || f.title || "";
    if (kind !== "audio" && opts.withSubs && f.subs.length) payload.subs = f.subs;
  }
  if (opts.quality && opts.quality !== "En iyi" && kind !== "audio") payload.quality = opts.quality;
  return sendAndShow([pageUrl], { payload });
}

api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg && msg.type === "send") return sendAndShow(msg.urls || [], { referer: msg.referer || "", kind: msg.kind || null });
    if (msg && msg.type === "status") {
      const opts = await getOptions();
      const app = await ping(opts.port);
      return { app, port: opts.port, intercept: opts.intercept, launchApp: opts.launchApp, lang: HI.currentLanguage(),
               downloads: app ? await appStatus(opts.port) : null };
    }
    // a click on a magnet link of a page (catch.js): DISO takes it, or the browser opens it as usual
    if (msg && msg.type === "magnet") {
      const opts = await getOptions();
      if (!opts.torrents || !HI.isTorrentLink(msg.url)) return { ok: false };
      return sendAndShow([msg.url], { referer: msg.referer || "" });
    }
    if (msg && msg.type === "page-torrents") return msg.tabId ? torrentLinksOf({ id: msg.tabId }) : [];
    if (msg && msg.type === "found") {
      const f = msg.tabId !== undefined ? await foundOn(msg.tabId) : null;
      const opts = await getOptions();
      return { media: f ? HI.rankMedia(f.media) : [], subs: f ? f.subs : [], title: f ? f.title : "",
               quality: opts.quality, withSubs: opts.withSubs, sniff: opts.sniff };
    }
    if (msg && msg.type === "stream") return hiddenStream(msg.url, sender);
    if (msg && msg.type === "send-found") return sendFound(msg.tabId, msg.urls || [], msg.kind, msg.quality, msg.withSubs);
    if (msg && msg.type === "episodes") {
      let tab = null;
      try { tab = await api.tabs.get(msg.tabId); } catch (e) { return { episodes: [], series: "" }; }
      return episodesOf(tab);
    }
    if (msg && msg.type === "series-start") {
      let tab = null;
      try { tab = await api.tabs.get(msg.tabId); } catch (e) { return { ok: false, text: HI.t("noEpisodes") }; }
      return startSeries(tab, msg.urls || [], msg.kind, msg.quality, msg.withSubs);
    }
    if (msg && msg.type === "series-status") return seriesStatus();
    if (msg && msg.type === "series-stop") {
      if (series.job) series.job.stop = true;
      return seriesStatus();
    }
    if (msg && msg.type === "send-page") {
      let tab = null;
      try { tab = await api.tabs.get(msg.tabId); } catch (e) { /* only the address then */ }
      return sendPage(tab || { id: msg.tabId, url: msg.url }, (tab && tab.url) || msg.url, msg.kind);
    }
    if (msg && msg.type === "open") return openApp();
    return null;
  })().then(sendResponse, (e) => sendResponse({ ok: false, text: String(e && e.message || e) }));
  return true;   // the answer comes later
});
