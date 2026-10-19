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

// The app answers /ping with {"app": "DISO", ...}. null = not running / something else.
async function ping(port) {
  try {
    const r = await fetch(HI.appBase(port) + "/ping", { cache: "no-store" });
    const data = await r.json();
    return data && data.app === HI.APP_ID ? data : null;
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

async function flash(text, ok) {
  const opts = await getOptions();
  if (!opts.badge) return;
  try {
    await api.action.setBadgeBackgroundColor({ color: ok ? "#2e9e5b" : "#b23b3b" });
    await api.action.setBadgeText({ text: text });
    setTimeout(() => api.action.setBadgeText({ text: "" }), 2500);
  } catch (e) { /* no toolbar button in this browser */ }
}

async function sendAndShow(urls, extra) {
  try {
    const result = await sendToApp(urls, extra);
    await flash(result.added ? "✓" : "=", true);
    return { ok: true, result, text: HI.describeResult(result) };
  } catch (e) {
    await flash("!", false);
    // a fetch that cannot connect throws a TypeError in every browser (the wording differs)
    const unreachable = e && e.name === "TypeError";
    return { ok: false, text: unreachable ? HI.t("unreachableOpen") : String(e && e.message || e) };
  }
}

// Every file link of the page in the tab (needs the page itself: a script runs there once).
async function fileLinksOf(tab) {
  const opts = await getOptions();
  try {
    const results = await api.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => Array.from(document.links, (a) => a.href),
    });
    const hrefs = [].concat(...(results || []).map((r) => r.result || []));
    return HI.pageFileLinks(hrefs, opts.extensions);
  } catch (e) {
    return [];                 // a page the browser does not let extensions read (its own pages, the store)
  }
}

// ------------------------------------------------------------------------ context menu
function createMenus() {
  api.contextMenus.removeAll(() => {
    api.contextMenus.create({ id: "hi-link", title: HI.t("menuLink"), contexts: ["link"] });
    api.contextMenus.create({ id: "hi-media", title: HI.t("menuLink"), contexts: ["video", "audio", "image"] });
    api.contextMenus.create({ id: "hi-page", title: HI.t("menuPage"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-all-links", title: HI.t("menuAllLinks"), contexts: ["page"] });
    api.contextMenus.create({ id: "hi-selection", title: HI.t("menuSelection"), contexts: ["selection"] });
  });
}
api.runtime.onInstalled.addListener(createMenus);

api.contextMenus.onClicked.addListener(async (info, tab) => {
  const referer = (tab && tab.url) || info.pageUrl || "";
  if (info.menuItemId === "hi-link") return sendAndShow([info.linkUrl], { referer });
  if (info.menuItemId === "hi-media") return sendAndShow([info.srcUrl], { referer });
  if (info.menuItemId === "hi-page") return sendAndShow([info.pageUrl || referer], { referer: "", kind: "video" });
  if (info.menuItemId === "hi-all-links") {
    const urls = tab ? await fileLinksOf(tab) : [];
    if (!urls.length) { await flash("0", false); return { ok: false, text: HI.t("noFileLinks") }; }
    return sendAndShow(urls, { referer });
  }
  if (info.menuItemId === "hi-selection") {
    const urls = HI.extractUrls(info.selectionText);
    if (!urls.length) return flash("?", false);
    return sendAndShow(urls, { referer });
  }
});

// -------------------------------------------------------------- take over browser downloads
api.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (bypass.has(url)) { bypass.delete(url); return; }
  const opts = await getOptions();
  if (!HI.shouldIntercept(item, opts)) return;
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
  try {
    await api.downloads.cancel(item.id);
    await api.downloads.erase({ id: item.id });
    const result = await sendToApp([url], { referer: item.referrer || "" });
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

api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg && msg.type === "send") return sendAndShow(msg.urls || [], { referer: msg.referer || "", kind: msg.kind || null });
    if (msg && msg.type === "status") {
      const opts = await getOptions();
      const app = await ping(opts.port);
      return { app, port: opts.port, intercept: opts.intercept, launchApp: opts.launchApp,
               downloads: app ? await appStatus(opts.port) : null };
    }
    if (msg && msg.type === "open") return openApp();
    return null;
  })().then(sendResponse, (e) => sendResponse({ ok: false, text: String(e && e.message || e) }));
  return true;   // the answer comes later
});
