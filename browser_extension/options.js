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
  $("launchApp").checked = o.launchApp;
}

async function save() {
  const port = Number($("port").value);
  if (!(port >= 1024 && port <= 65535)) { $("msg").textContent = HI.t("badPort"); return false; }
  await api.storage.local.set({
    port,
    intercept: $("intercept").checked,
    minSizeMB: Math.max(0, Number($("minSizeMB").value) || 0),
    extensions: HI.parseExtensions($("extensions").value).join(","),
    badge: $("badge").checked,
    launchApp: $("launchApp").checked,
  });
  $("msg").textContent = HI.t("saved");
  return true;
}

async function test() {
  if (!(await save())) return;
  try {
    const r = await fetch(HI.appBase($("port").value) + "/ping", { cache: "no-store" });
    const d = await r.json();
    $("msg").textContent = d.app === HI.APP_ID ? HI.t("connected", [d.version]) : HI.t("otherApp");
  } catch (e) {
    $("msg").textContent = HI.t("unreachableLong");
  }
}

HI.translatePage(document);
$("save").addEventListener("click", save);
$("test").addEventListener("click", test);
load();
