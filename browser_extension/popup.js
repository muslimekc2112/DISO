"use strict";
const api = typeof browser !== "undefined" ? browser : chrome;
const $ = (id) => document.getElementById(id);
let torrents = [];                       // the magnet links / .torrent files of the page in the tab
let lastStatus = null;
let foundMedia = [];                     // 🎞 the videos the page played (background.js found them)
let foundSubs = [];
const chosen = new Set();

function ask(message) {
  return new Promise((resolve) => api.runtime.sendMessage(message, resolve));
}

async function activeTab() {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  return tab;
}

// Every text in the language of the moment: the one chosen here, or DISO's.
async function useLanguage(code) {
  const o = Object.assign({}, HI.DEFAULTS, await api.storage.local.get(HI.DEFAULTS));
  HI.setLanguage(code || HI.pickLanguage(o.lang, o.appLang));
  HI.translatePage(document);
  $("lang-tr").className = HI.currentLanguage() === "tr" ? "on" : "";
  $("lang-en").className = HI.currentLanguage() === "en" ? "on" : "";
  showTorrents();
  showFound();
  if (lastStatus) show(lastStatus);
}

function show(s) {
  lastStatus = s;
  const on = !!(s && s.app);
  $("dot").className = "dot" + (on ? " on" : "");
  $("state").textContent = on ? HI.t("appRuns", [s.app.version]) : (s && s.launchApp ? HI.t("appClosed") : HI.t("unreachableOpen"));
  $("downloads").textContent = on ? HI.statusText(s.downloads) : "";
  $("intercept").checked = !!(s && s.intercept);
  const list = $("list");
  list.textContent = "";
  if (!on) return;
  const { rows, more } = HI.downloadRows(s.downloads);
  rows.forEach((r) => {
    const row = document.createElement("div");
    row.className = "row" + (r.queued ? " queued" : "");
    const top = document.createElement("div");
    top.className = "top";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = name.title = r.name;
    const detail = document.createElement("span");
    detail.className = "detail";
    detail.textContent = r.detail;
    top.append(name, detail);
    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = Math.round(r.fraction * 100) + "%";
    bar.append(fill);
    row.append(top, bar);
    list.append(row);
  });
  if (more > 0) {
    const line = document.createElement("div");
    line.className = "more";
    line.textContent = HI.t("moreDownloads", [more]);
    list.append(line);
  }
}

async function refresh() {
  const s = await ask({ type: "status" });
  if (s && s.lang && s.lang !== HI.currentLanguage() && !pinned) await useLanguage(s.lang);   // DISO changed its language
  show(s);
}

function showTorrents() {
  const b = $("torrents");
  b.hidden = !torrents.length;
  b.textContent = torrents.length === 1 ? HI.t("torrentOnPage") : HI.t("torrentsOnPage", [torrents.length]);
}

async function findTorrents() {
  const tab = await activeTab();
  torrents = tab && tab.id ? (await ask({ type: "page-torrents", tabId: tab.id })) || [] : [];
  showTorrents();
}

// ------------------------------------------------------------------ 🎞 found videos
function showFound() {
  const box = $("found");
  if (!box) return;
  $("foundTitle").textContent = foundMedia.length ? HI.t("foundCount", [foundMedia.length]) : HI.t("foundTitle");
  $("foundNone").hidden = foundMedia.length > 0;
  $("allNone").hidden = foundMedia.length < 2;
  $("foundVideo").hidden = $("foundAudio").hidden = foundMedia.length === 0;
  $("subsRow").hidden = foundSubs.length === 0;
  $("subsFound").textContent = foundSubs.length ? HI.t("foundSubs", [foundSubs.length]) : "";
  const list = $("media");
  list.textContent = "";
  foundMedia.forEach((m) => {
    const row = document.createElement("label");
    row.className = "media-row";
    const box2 = document.createElement("input");
    box2.type = "checkbox";
    box2.checked = chosen.has(m.url);
    box2.addEventListener("change", () => { if (box2.checked) chosen.add(m.url); else chosen.delete(m.url); });
    const text = document.createElement("span");
    text.textContent = HI.mediaLine(m);
    text.title = m.url;
    row.append(box2, text);
    list.append(row);
  });
}

async function findVideos() {
  const tab = await activeTab();
  const r = tab && tab.id !== undefined ? await ask({ type: "found", tabId: tab.id }) : null;
  if (!r) return;
  $("found").hidden = !r.sniff;
  const before = new Set(foundMedia.map((m) => m.url));
  foundMedia = r.media || [];
  foundSubs = r.subs || [];
  if (!before.size && foundMedia.length) chosen.add(foundMedia[0].url);   // the best guess is chosen
  if (!pickedQuality) $("quality").value = r.quality || "En iyi";
  if (!pickedSubs) $("withSubs").checked = r.withSubs !== false;
  showFound();
}

let pickedQuality = false;
let pickedSubs = false;
async function sendFound(kind) {
  const tab = await activeTab();
  if (!chosen.size) { $("msg").textContent = HI.t("nothingChosen"); return; }
  const r = await ask({ type: "send-found", tabId: tab.id, urls: Array.from(chosen), kind,
                        quality: $("quality").value, withSubs: $("withSubs").checked });
  $("msg").textContent = r ? r.text : HI.t("noAnswer");
  refresh();
}

async function send(urls, extra) {
  const r = await ask(Object.assign({ type: "send", urls }, extra || {}));
  $("msg").textContent = r ? r.text : HI.t("noAnswer");
  refresh();
  return r;
}

async function sendTab(kind) {
  const tab = await activeTab();
  if (!tab || !tab.url) return;
  // the page itself, with the videos it played for when DISO cannot read the site
  const r = await ask({ type: "send-page", tabId: tab.id, url: tab.url, kind });
  $("msg").textContent = r ? r.text : HI.t("noAnswer");
  refresh();
}

async function sendTorrents() {
  const tab = await activeTab();
  if (torrents.length) send(torrents, { referer: (tab && tab.url) || "" });
}

async function sendPasted() {
  const urls = HI.extractUrls($("paste").value);
  if (!urls.length) { $("msg").textContent = HI.t("nothingToSend"); return; }
  const r = await send(urls);
  if (r && r.ok) $("paste").value = "";
}

async function openApp() {
  $("msg").textContent = HI.t("opening");
  const r = await ask({ type: "open" });
  $("msg").textContent = r && r.ok ? "" : (r && r.text) || HI.t("openFailed");
  refresh();
}

// TR | EN at the top: a choice of its own (kept), until "Same as DISO" is chosen in the settings
let pinned = false;
async function pickLanguage(code) {
  pinned = true;
  await api.storage.local.set({ lang: code });
  await useLanguage(code);
}

$("video").addEventListener("click", () => sendTab("video"));
$("audio").addEventListener("click", () => sendTab("audio"));
$("torrents").addEventListener("click", sendTorrents);
$("pasteGo").addEventListener("click", sendPasted);
$("paste").addEventListener("keydown", (e) => { if (e.key === "Enter") sendPasted(); });
$("open").addEventListener("click", openApp);
$("lang-tr").addEventListener("click", () => pickLanguage("tr"));
$("lang-en").addEventListener("click", () => pickLanguage("en"));
$("intercept").addEventListener("change", (e) => api.storage.local.set({ intercept: e.target.checked }));
$("options").addEventListener("click", () => api.runtime.openOptionsPage());
$("foundVideo").addEventListener("click", () => sendFound("video"));
$("foundAudio").addEventListener("click", () => sendFound("audio"));
$("quality").addEventListener("change", () => { pickedQuality = true; });
$("withSubs").addEventListener("change", () => { pickedSubs = true; });
$("allNone").addEventListener("click", () => {
  if (chosen.size === foundMedia.length) chosen.clear();
  else foundMedia.forEach((m) => chosen.add(m.url));
  showFound();
});
(async () => {
  const o = Object.assign({}, HI.DEFAULTS, await api.storage.local.get(HI.DEFAULTS));
  pinned = o.lang === "tr" || o.lang === "en";
  await useLanguage();
  refresh();
  findTorrents();
  findVideos();
  setInterval(refresh, 2000);            // the downloads stay live while the popup is open
  setInterval(findVideos, 1500);         // ... and so do the videos the page plays
})();
