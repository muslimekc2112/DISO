"use strict";
const api = typeof browser !== "undefined" ? browser : chrome;
const $ = (id) => document.getElementById(id);

function ask(message) {
  return new Promise((resolve) => api.runtime.sendMessage(message, resolve));
}

async function refresh() {
  const s = await ask({ type: "status" });
  const on = !!(s && s.app);
  $("dot").className = "dot" + (on ? " on" : "");
  $("state").textContent = on ? HI.t("appRuns", [s.app.version]) : (s && s.launchApp ? HI.t("appClosed") : HI.t("unreachableOpen"));
  $("downloads").textContent = on ? HI.statusText(s.downloads) : "";
  $("intercept").checked = !!(s && s.intercept);
}

async function sendTab(kind) {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url) return;
  const r = await ask({ type: "send", urls: [tab.url], kind });
  $("msg").textContent = r ? r.text : HI.t("noAnswer");
  refresh();
}

async function openApp() {
  $("msg").textContent = HI.t("opening");
  const r = await ask({ type: "open" });
  $("msg").textContent = r && r.ok ? "" : (r && r.text) || HI.t("openFailed");
  refresh();
}

HI.translatePage(document);
$("video").addEventListener("click", () => sendTab("video"));
$("audio").addEventListener("click", () => sendTab("audio"));
$("open").addEventListener("click", openApp);
$("intercept").addEventListener("change", (e) => api.storage.local.set({ intercept: e.target.checked }));
$("options").addEventListener("click", () => api.runtime.openOptionsPage());
refresh();
setInterval(refresh, 2000);              // the downloads line stays live while the popup is open
