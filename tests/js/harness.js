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

const listeners = { installed: [], menu: [], created: [], message: [] };
const log = { badge: [], menus: [], cancelled: [], erased: [], downloaded: [], cookiesAsked: [], native: [], paused: [],
              resumed: [], scripted: [] };
const PAGE_LINKS = ["http://shop.example/a.zip", "http://shop.example/page.html", "http://shop.example/b.mp4#t=1",
                    "http://shop.example/a.zip", "http://shop.example/p.jpg", "javascript:void(0)"];
const store = { port };
const cookieJar = { [SESSION_URL]: [{ name: "sid", value: "1" }, { name: "theme", value: "dark" }] };

// like a browser: every request from the extension carries its chrome-extension:// Origin
const extensionFetch = (url, init = {}) =>
  fetch(url, { ...init, headers: { ...(init.headers || {}), Origin: "chrome-extension://testextensionid" } });

const chrome = {
  storage: { local: {
    get: async (defaults) => ({ ...defaults, ...store }),
    set: async (o) => { Object.assign(store, o); },
  } },
  cookies: { getAll: async ({ url }) => { log.cookiesAsked.push(url); return cookieJar[url] || []; } },
  contextMenus: {
    removeAll: (cb) => cb(),
    create: (o) => log.menus.push(o.id),
    onClicked: { addListener: (f) => listeners.menu.push(f) },
  },
  runtime: {
    onInstalled: { addListener: (f) => listeners.installed.push(f) },
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
    setBadgeText: async (o) => { log.badge.push(o.text); },
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
const created = (item) => Promise.all(listeners.created.map((f) => f(item)));

(async () => {
  let answer = null;
  const page = "http://shop.example/page";
  if (scenario === "menus") {
    for (const f of listeners.installed) f();
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
  } else if (scenario === "unknown-message") {
    answer = await ask({ type: "nonsense" });
  } else {
    throw new Error("unknown scenario " + scenario);
  }
  console.log(JSON.stringify({ answer, log }));
})().catch((e) => { console.log(JSON.stringify({ error: String(e && e.stack || e) })); process.exit(1); });
