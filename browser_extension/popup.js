"use strict";
const api = typeof browser !== "undefined" ? browser : chrome;
const $ = (id) => document.getElementById(id);
let torrents = [];                       // the magnet links / .torrent files of the page in the tab
let lastStatus = null;

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

async function send(urls, extra) {
  const r = await ask(Object.assign({ type: "send", urls }, extra || {}));
  $("msg").textContent = r ? r.text : HI.t("noAnswer");
  refresh();
  return r;
}

async function sendTab(kind) {
  const tab = await activeTab();
  if (!tab || !tab.url) return;
  send([tab.url], { kind });
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
(async () => {
  const o = Object.assign({}, HI.DEFAULTS, await api.storage.local.get(HI.DEFAULTS));
  pinned = o.lang === "tr" || o.lang === "en";
  await useLanguage();
  refresh();
  findTorrents();
  setInterval(refresh, 2000);            // the downloads stay live while the popup is open
})();
