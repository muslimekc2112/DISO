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
  $("state").textContent = on ? "Uygulama çalışıyor (v" + s.app.version + ")" : "Uygulama kapalı — DISO'yi aç";
  $("page").disabled = $("audio").disabled = !on;
  $("intercept").checked = !!(s && s.intercept);
}

async function sendTab(kind) {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url) return;
  const r = await ask({ type: "send", urls: [tab.url], kind });
  $("msg").textContent = r ? r.text : "Cevap yok";
}

$("page").addEventListener("click", () => sendTab("auto"));
$("audio").addEventListener("click", () => sendTab("audio"));
$("intercept").addEventListener("change", (e) => api.storage.local.set({ intercept: e.target.checked }));
$("options").addEventListener("click", () => api.runtime.openOptionsPage());
refresh();
