"use strict";
const api = typeof browser !== "undefined" ? browser : chrome;
const $ = (id) => document.getElementById(id);

async function load() {
  const o = Object.assign({}, HI.DEFAULTS, await api.storage.local.get(HI.DEFAULTS));
  $("port").value = o.port;
  $("intercept").checked = o.intercept;
  $("minSizeMB").value = o.minSizeMB;
  $("extensions").value = o.extensions;
  $("badge").checked = o.badge;
}

async function save() {
  const port = Number($("port").value);
  if (!(port >= 1024 && port <= 65535)) { $("msg").textContent = "Port 1024 ile 65535 arasında olmalı."; return false; }
  await api.storage.local.set({
    port,
    intercept: $("intercept").checked,
    minSizeMB: Math.max(0, Number($("minSizeMB").value) || 0),
    extensions: HI.parseExtensions($("extensions").value).join(","),
    badge: $("badge").checked,
  });
  $("msg").textContent = "Kaydedildi.";
  return true;
}

async function test() {
  if (!(await save())) return;
  try {
    const r = await fetch(HI.appBase($("port").value) + "/ping", { cache: "no-store" });
    const d = await r.json();
    $("msg").textContent = d.app === HI.APP_ID ? "✓ Uygulamaya bağlanıldı (v" + d.version + ")" : "Bu portta başka bir şey çalışıyor.";
  } catch (e) {
    $("msg").textContent = "Uygulamaya ulaşılamadı. Hızlı İndirici açık mı, port doğru mu?";
  }
}

$("save").addEventListener("click", save);
$("test").addEventListener("click", test);
load();
