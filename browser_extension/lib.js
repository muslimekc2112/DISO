// Pure helpers of the extension (no browser API): easy to test with node.
(function (root, factory) {
  const lib = factory();
  if (typeof module === "object" && module.exports) module.exports = lib;
  else root.HI = lib;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  const APP_ID = "DISO";

  const DEFAULTS = {
    port: 17653,           // must be the same as "Eklenti bağlantı noktası" in the app's settings
    intercept: false,      // take over the browser's own downloads
    minSizeMB: 5,          // ... of this size or bigger (0 = only by file type)
    extensions: "zip,rar,7z,tar,gz,iso,exe,msi,apk,dmg,mp4,mkv,avi,mov,webm,mp3,flac,wav,pdf",
    badge: true,           // show a short tick on the toolbar button after sending
  };

  function appBase(port) {
    return "http://127.0.0.1:" + Number(port || DEFAULTS.port);
  }

  function isHttpUrl(u) {
    return typeof u === "string" && /^https?:\/\/[^\s]+$/i.test(u);
  }

  // "ZIP, .rar ,7z" -> ["zip", "rar", "7z"]
  function parseExtensions(text) {
    const seen = new Set();
    String(text || "").split(/[\s,;]+/).forEach((e) => {
      e = e.trim().replace(/^\./, "").toLowerCase();
      if (e) seen.add(e);
    });
    return Array.from(seen);
  }

  // "C:\\a\\b.TAR.GZ?x=1" -> "gz"; "file" -> ""
  function fileExtension(nameOrUrl) {
    let s = String(nameOrUrl || "").split("#")[0].split("?")[0];
    s = s.slice(Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\")) + 1);
    const i = s.lastIndexOf(".");
    return i > 0 && i < s.length - 1 ? s.slice(i + 1).toLowerCase() : "";
  }

  // every http(s) link of a text, in order, without repeats
  function extractUrls(text) {
    const found = String(text || "").match(/https?:\/\/[^\s<>"']+/gi) || [];
    const out = [];
    found.forEach((raw) => {
      let u = raw.replace(/[.,;]+$/, "");
      while (/[)\]]$/.test(u)) {
        const close = u.slice(-1), open = close === ")" ? "(" : "[";
        if (u.split(close).length - 1 > u.split(open).length - 1) u = u.slice(0, -1).replace(/[.,;]+$/, "");
        else break;
      }
      if (isHttpUrl(u) && !out.includes(u)) out.push(u);
    });
    return out;
  }

  // chrome.cookies.getAll() result -> the value of a Cookie header
  function cookieHeader(cookies) {
    return (cookies || []).filter((c) => c && c.name).map((c) => c.name + "=" + c.value).join("; ");
  }

  // Should the extension take this browser download over? `item` is a chrome DownloadItem.
  function shouldIntercept(item, opts) {
    if (!opts || !opts.intercept || !item) return false;
    if (item.byExtensionId) return false;              // started by an extension: not ours to take
    const url = item.finalUrl || item.url;
    if (!isHttpUrl(url)) return false;                 // blob:, data:, file: ... cannot be fetched again
    const ext = fileExtension(item.filename || url);
    if (ext && parseExtensions(opts.extensions).includes(ext)) return true;
    const size = item.fileSize > 0 ? item.fileSize : item.totalBytes > 0 ? item.totalBytes : 0;
    return Number(opts.minSizeMB) > 0 && size >= Number(opts.minSizeMB) * 1024 * 1024;
  }

  // the body of POST /add
  function buildPayload({ urls, referer, userAgent, cookies, kind }) {
    const p = { urls: (urls || []).filter(isHttpUrl) };
    if (referer && isHttpUrl(referer)) p.referer = referer;
    if (userAgent) p.userAgent = String(userAgent);
    if (cookies) p.cookies = String(cookies);
    if (["auto", "video", "audio", "file"].includes(kind)) p.kind = kind;
    return p;
  }

  function describeResult(r) {
    if (!r) return "Uygulamaya ulaşılamadı";
    if (r.added && r.duplicates) return r.added + " eklendi, " + r.duplicates + " zaten listedeydi";
    if (r.added) return r.added + " bağlantı eklendi";
    if (r.duplicates) return "Zaten listede";
    return "Eklenmedi";
  }

  return { APP_ID, DEFAULTS, appBase, isHttpUrl, parseExtensions, fileExtension, extractUrls,
           cookieHeader, shouldIntercept, buildPayload, describeResult };
});
