// Runs the extension's background script (browser_extension/background.js) against a mock of
// the browser API, talking REAL HTTP to the app's bridge.
//   node harness.js <port> <scenario> [live port]      prints a JSON report on the last line
// The native host is pretended: asked to start DISO it "starts" the app on [live port] (or fails without one).
"use strict";
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const EXT = path.join(__dirname, "..", "..", "browser_extension");
const port = Number(process.argv[2]);
const scenario = process.argv[3];
const livePort = Number(process.argv[4] || 0);
const SESSION_URL = "http://shop.example/files/report.zip";

const listeners = { installed: [], startup: [], menu: [], created: [], message: [], storage: [], sendHeaders: [],
                    response: [], tabUpdated: [], tabRemoved: [] };
const session = {};
const log = { badge: [], menus: [], titles: [], cancelled: [], erased: [], downloaded: [], cookiesAsked: [], native: [], paused: [],
              resumed: [], scripted: [] };
const PAGE_LINKS = ["http://shop.example/a.zip", "http://shop.example/page.html", "http://shop.example/b.mp4#t=1",
                    "http://shop.example/a.zip", "http://shop.example/p.jpg", "javascript:void(0)",
                    "magnet:?xt=urn:btih:AAA&dn=one", "http://shop.example/two.torrent", "magnet:?xt=urn:btih:aaa&dn=again"];
const store = { port };
const cookieJar = { [SESSION_URL]: [{ name: "sid", value: "1" }, { name: "theme", value: "dark" }] };

// like a browser: every request from the extension carries its chrome-extension:// Origin
const extensionFetch = (url, init = {}) =>
  fetch(url, { ...init, headers: { ...(init.headers || {}), Origin: "chrome-extension://testextensionid" } });

const chrome = {
  storage: { local: {
    get: async (defaults) => ({ ...defaults, ...store }),
    set: async (o) => { Object.assign(store, o); },
  }, session: {
    get: async (key) => (key in session ? { [key]: session[key] } : {}),
    set: async (o) => { Object.assign(session, o); },
    remove: async (key) => { delete session[key]; },
  }, onChanged: { addListener: (f) => listeners.storage.push(f) } },
  cookies: { getAll: async ({ url }) => { log.cookiesAsked.push(url); return cookieJar[url] || []; } },
  contextMenus: {
    removeAll: (cb) => { log.menus = []; log.titles = []; cb(); },
    create: (o) => { log.menus.push(o.id); log.titles.push(o.title); },
    onClicked: { addListener: (f) => listeners.menu.push(f) },
  },
  runtime: {
    onInstalled: { addListener: (f) => listeners.installed.push(f) },
    onStartup: { addListener: (f) => listeners.startup.push(f) },
    onMessage: { addListener: (f) => listeners.message.push(f) },
    sendNativeMessage: async (host, message) => {
      log.native.push({ host, message });
      if (!livePort) throw new Error("Specified native messaging host not found.");
      store.port = livePort;                 // DISO is up now (on the live port)
      return { ok: true, started: true };
    },
  },
  scripting: {
    executeScript: async ({ target }) => { log.scripted.push(target.tabId); return [{ result: PAGE_LINKS }]; },
  },
  downloads: {
    onCreated: { addListener: (f) => listeners.created.push(f) },
    cancel: async (id) => { log.cancelled.push(id); },
    erase: async (q) => { log.erased.push(q.id); },
    pause: async (id) => { log.paused.push(id); },
    resume: async (id) => { log.resumed.push(id); },
    search: async (q) => [{ id: q.id, state: finished.has(q.id) ? "complete" : "in_progress" }],
    download: async (o) => {               // the browser starts it again: that fires onCreated
      log.downloaded.push(o.url);
      for (const f of listeners.created) await f({ id: 99, url: o.url, filename: "report.zip", fileSize: 10 });
      return 99;
    },
  },
  action: {
    setBadgeBackgroundColor: async () => {},
    setBadgeText: async (o) => { log.badge.push(o.tabId !== undefined ? o.tabId + ":" + o.text : o.text); },
  },
  webRequest: {
    OnSendHeadersOptions: { EXTRA_HEADERS: "extraHeaders" },
    onSendHeaders: { addListener: (f, filter, extra) => { listeners.sendHeaders.push(f); log.webRequestExtra = extra; } },
    onResponseStarted: { addListener: (f) => listeners.response.push(f) },
    onErrorOccurred: { addListener: () => {} },
  },
  tabs: {
    get: async (id) => ({ id, url: "http://films.example/watch/film-1", title: "Güzel Bir Film İzle" }),
    onUpdated: { addListener: (f) => listeners.tabUpdated.push(f) },
    onRemoved: { addListener: (f) => listeners.tabRemoved.push(f) },
  },
};

const finished = new Set();              // downloads the browser has finished meanwhile

const context = vm.createContext({ chrome, fetch: extensionFetch, navigator: { userAgent: "TestBrowser/1.0" },
                                   setTimeout: (f) => 0 && f, console, URL });
for (const file of ["lib.js", "background.js"]) {
  vm.runInContext(fs.readFileSync(path.join(EXT, file), "utf8"), context, { filename: file });
}

const ask = (msg) => new Promise((resolve) => listeners.message[0](msg, {}, resolve));
const click = (info, tab) => listeners.menu[0](info, tab);
// the page in tab 9 plays: what its player asks for, with the headers the browser sends
let reqId = 0;
async function played(url, type, contentType, size, tabId = 9) {
  const requestId = String(++reqId);
  const requestHeaders = [{ name: "Referer", value: "http://player.example/embed/77" }, { name: "Origin", value: "http://player.example" },
                          { name: "Cookie", value: "pl=1" }, { name: "User-Agent", value: "TestBrowser/1.0" }];
  for (const f of listeners.sendHeaders) f({ requestId, url, tabId, type, requestHeaders });
  const responseHeaders = [{ name: "Content-Type", value: contentType }];
  if (size) responseHeaders.push({ name: "Content-Length", value: String(size) });
  for (const f of listeners.response) await f({ requestId, url, tabId, type, statusCode: 200, responseHeaders,
                                                initiator: "http://player.example" });
}
const created = (item) => Promise.all(listeners.created.map((f) => f(item)));

(async () => {
  let answer = null;
  const page = "http://shop.example/page";
  if (scenario === "menus") {
    for (const f of listeners.installed) f();
  } else if (scenario === "language") {
    // DISO answers in English: the menus follow, and the language is kept for when DISO is closed
    answer = await ask({ type: "status" });
    await new Promise((r) => setImmediate(r));
  } else if (scenario === "language-fixed") {
    store.lang = "tr";                     // chosen in the settings: DISO's English does not change it
    answer = await ask({ type: "status" });
  } else if (scenario === "torrents") {
    answer = await click({ menuItemId: "hi-torrents", pageUrl: page }, { id: 5, url: page });
  } else if (scenario === "magnet") {
    answer = await ask({ type: "magnet", url: "magnet:?xt=urn:btih:AAA&dn=one", referer: page });
  } else if (scenario === "magnet-off") {
    store.torrents = false;
    answer = await ask({ type: "magnet", url: "magnet:?xt=urn:btih:AAA&dn=one", referer: page });
  } else if (scenario === "page-torrents") {
    answer = await ask({ type: "page-torrents", tabId: 5 });
  } else if (scenario === "intercept-torrent") {
    // "intercept" is off, but a .torrent file always goes to DISO
    await created({ id: 8, url: "http://shop.example/get?id=2", filename: "C:\\dl\\ubuntu.torrent", fileSize: 900,
                    referrer: page, state: "in_progress", startTime: new Date().toISOString() });
  } else if (scenario === "link") {
    answer = await click({ menuItemId: "hi-link", linkUrl: SESSION_URL }, { url: page });
  } else if (scenario === "media") {
    answer = await click({ menuItemId: "hi-media", srcUrl: "http://shop.example/v.mp4" }, { url: page });
  } else if (scenario === "page") {
    answer = await click({ menuItemId: "hi-page-video", pageUrl: "http://video.example/watch?v=1" }, { url: "http://video.example/watch?v=1" });
  } else if (scenario === "page-audio") {
    answer = await click({ menuItemId: "hi-page-audio", pageUrl: "http://video.example/watch?v=1" }, { url: "http://video.example/watch?v=1" });
  } else if (scenario === "page-link") {
    answer = await click({ menuItemId: "hi-link", linkUrl: "http://video.example/watch?v=2" }, { url: page });
  } else if (scenario === "mixed-selection") {
    answer = await click({ menuItemId: "hi-selection", selectionText: "http://a.com/setup.exe http://a.com/watch?v=1 http://a.com/b.rar" }, { url: page });
  } else if (scenario === "selection") {
    answer = await click({ menuItemId: "hi-selection", selectionText: "a http://a.com/1 b (https://b.org/2). http://a.com/1" }, { url: page });
  } else if (scenario === "empty-selection") {
    answer = await click({ menuItemId: "hi-selection", selectionText: "nothing" }, { url: page });
  } else if (scenario === "intercept") {
    store.intercept = true;
    await created({ id: 7, url: SESSION_URL, filename: "C:\\dl\\report.zip", fileSize: 10, referrer: page,
                    state: "in_progress", startTime: new Date().toISOString() });
  } else if (scenario === "intercept-finished") {
    // a small file: done in the browser before DISO has answered
    store.intercept = true;
    finished.add(7);
    await created({ id: 7, url: SESSION_URL, filename: "report.zip", fileSize: 10, referrer: page,
                    state: "in_progress", startTime: new Date().toISOString() });
  } else if (scenario === "intercept-history") {
    // what the browser reports when it starts: the downloads of its history, finished or broken off
    store.intercept = true;
    const day = new Date(Date.now() - 86400000).toISOString();
    await created({ id: 1, url: SESSION_URL, filename: "C:\\dl\\report.zip", fileSize: 10, state: "complete", startTime: day });
    await created({ id: 2, url: "http://shop.example/b.rar", filename: "b.rar", fileSize: 10, state: "interrupted", startTime: day });
    await created({ id: 3, url: "http://shop.example/c.iso", filename: "c.iso", fileSize: 10, state: "in_progress", startTime: day });
  } else if (scenario === "intercept-before-ready") {
    // just added to a browser that was downloading 20 s ago: the browser reports it, still "in progress"
    store.intercept = true;
    await created({ id: 4, url: SESSION_URL, filename: "report.zip", fileSize: 10, referrer: page,
                    state: "in_progress", startTime: new Date(Date.now() - 20000).toISOString() });
  } else if (scenario === "intercept-off") {
    await created({ id: 7, url: SESSION_URL, filename: "report.zip", fileSize: 10 });
  } else if (scenario === "intercept-small") {
    store.intercept = true;
    await created({ id: 7, url: "http://shop.example/p.jpg", filename: "p.jpg", fileSize: 100 });
  } else if (scenario === "intercept-blob") {
    store.intercept = true;
    await created({ id: 7, url: "blob:http://shop.example/1", filename: "report.zip", fileSize: 99999999 });
  } else if (scenario === "all-links") {
    answer = await click({ menuItemId: "hi-all-links", pageUrl: page }, { id: 5, url: page });
  } else if (scenario === "launch-off") {
    store.launchApp = false;
    answer = await click({ menuItemId: "hi-link", linkUrl: SESSION_URL }, { url: page });
  } else if (scenario === "open") {
    answer = await ask({ type: "open" });
  } else if (scenario === "send") {
    answer = await ask({ type: "send", urls: ["http://a.com/1", "http://a.com/2"], referer: page, kind: "audio" });
  } else if (scenario === "status") {
    answer = await ask({ type: "status" });
  } else if (scenario === "sniff") {
    await played("http://cdn.example/hls/master.m3u8?token=a", "xmlhttprequest", "application/vnd.apple.mpegurl", 900);
    await played("http://cdn.example/hls/720/index.m3u8?token=a", "xmlhttprequest", "application/vnd.apple.mpegurl", 700);
    await played("http://cdn.example/hls/720/seg-1.ts", "xmlhttprequest", "video/mp2t", 900000);
    await played("http://cdn.example/hls/720/seg-2.ts", "xmlhttprequest", "video/mp2t", 900000);
    await played("http://cdn.example/subs/turkce.vtt", "xmlhttprequest", "text/vtt", 3000);
    await played("http://ads.example/pixel.mp4", "media", "video/mp4", 2000);                    // too small: an advert's pixel
    await played("http://cdn.example/hls/master.m3u8?token=a", "xmlhttprequest", "application/vnd.apple.mpegurl", 900);
    await played("http://other.example/clip.mp4", "media", "video/mp4", 5000000, 4);            // another tab
    const found = await ask({ type: "found", tabId: 9 });
    const sent = await ask({ type: "send-found", tabId: 9, urls: found.media.map((m) => m.url), kind: "video",
                             quality: "720p", withSubs: true });
    const page = await ask({ type: "send-page", tabId: 9, url: "http://films.example/watch/film-1", kind: "video" });
    for (const f of listeners.tabUpdated) f(9, { status: "loading", url: "http://films.example/watch/film-2" });
    const after = await ask({ type: "found", tabId: 9 });
    answer = { found, sent, page, after };
  } else if (scenario === "sniff-off") {
    store.sniff = false;
    await played("http://cdn.example/hls/master.m3u8", "xmlhttprequest", "application/vnd.apple.mpegurl", 900);
    answer = await ask({ type: "found", tabId: 9 });
  } else if (scenario === "unknown-message") {
    answer = await ask({ type: "nonsense" });
  } else {
    throw new Error("unknown scenario " + scenario);
  }
  console.log(JSON.stringify({ answer, log, store }));
})().catch((e) => { console.log(JSON.stringify({ error: String(e && e.stack || e) })); process.exit(1); });
