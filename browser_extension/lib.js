// Pure helpers of the extension (no browser API): easy to test with node.
(function (root, factory) {
  const lib = factory();
  if (typeof module === "object" && module.exports) module.exports = lib;
  else root.HI = lib;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  const APP_ID = "DISO";

  const DEFAULTS = {
    port: 17653,           // must be the same as "Extension port" in the app's settings
    intercept: false,      // take over the browser's own downloads
    minSizeMB: 5,          // ... of this size or bigger (0 = only by file type)
    extensions: "zip,rar,7z,tar,gz,iso,exe,msi,apk,dmg,mp4,mkv,avi,mov,webm,mp3,flac,wav,pdf",
    badge: true,           // show a short tick on the toolbar button after sending
  };

  // Every text the extension shows, in Turkish and English; "{0}", "{1}" are the changing parts.
  const TEXTS = {
    tr: {
      checking: "Kontrol ediliyor…", sendTab: "⬇ Bu sekmeyi indir", sendTabAudio: "🎵 Bu sekmeyi MP3 olarak indir",
      catchDownloads: "Tarayıcı indirmelerini yakala", settings: "⚙ Ayarlar",
      appRuns: "Uygulama çalışıyor (v{0})", appClosed: "Uygulama kapalı — DISO'yu aç", noAnswer: "Cevap yok",
      optionsTitle: "DISO — Ayarlar", port: "Bağlantı noktası",
      portHint: "Uygulamadaki Ayarlar → \"Eklenti bağlantı noktası\" ile aynı olmalı.",
      redirect: "Tarayıcı indirmelerini DISO'ya yönlendir",
      redirectHint: "Uygulama kapalıysa indirme tarayıcıda normal şekilde devam eder.",
      minSize: "En az boyut (MB)", minSizeHint: "Bu boyuttan büyük indirmeler yakalanır. 0: yalnızca aşağıdaki dosya türleri.",
      types: "Her zaman yakalanacak dosya türleri", badge: "Gönderince araç çubuğu simgesinde ✓ göster",
      save: "Kaydet", test: "Bağlantıyı dene", badPort: "Port 1024 ile 65535 arasında bir sayı olsun.", saved: "Kaydedildi.",
      connected: "✓ Uygulamaya bağlanıldı (v{0})", otherApp: "Bu portta başka bir şey çalışıyor.",
      unreachableLong: "Uygulamaya ulaşılamadı. DISO açık mı, port doğru mu?",
      unreachable: "Uygulamaya ulaşılamadı", unreachableOpen: "Uygulamaya ulaşılamadı: DISO açık mı?",
      bridgeOff: "Uygulamada tarayıcı eklentisi kapalı", refused: "Uygulama reddetti: {0}",
      addedAndDuplicates: "{0} eklendi, {1} zaten listedeydi", added: "{0} bağlantı eklendi",
      alreadyListed: "Zaten listede", notAdded: "Eklenmedi",
      menuLink: "DISO ile indir", menuPage: "Bu sayfayı DISO ile indir (video)",
      menuSelection: "Seçilen bağlantıları DISO ile indir",
    },
    en: {
      checking: "Checking…", sendTab: "⬇ Download this tab", sendTabAudio: "🎵 Download this tab as MP3",
      catchDownloads: "Catch browser downloads", settings: "⚙ Settings",
      appRuns: "The app is running (v{0})", appClosed: "The app is closed — open DISO", noAnswer: "No answer",
      optionsTitle: "DISO — Settings", port: "Port",
      portHint: "Must be the same as Settings → \"Extension port\" in the app.",
      redirect: "Send browser downloads to DISO",
      redirectHint: "If the app is closed, the download goes on in the browser as usual.",
      minSize: "Minimum size (MB)", minSizeHint: "Downloads bigger than this are caught. 0: only the file types below.",
      types: "File types that are always caught", badge: "Show ✓ on the toolbar button after sending",
      save: "Save", test: "Test the connection", badPort: "The port must be a number from 1024 to 65535.", saved: "Saved.",
      connected: "✓ Connected to the app (v{0})", otherApp: "Something else is running on this port.",
      unreachableLong: "Could not reach the app. Is DISO open, is the port right?",
      unreachable: "Could not reach the app", unreachableOpen: "Could not reach the app: is DISO open?",
      bridgeOff: "The browser extension is switched off in the app", refused: "The app refused: {0}",
      addedAndDuplicates: "{0} added, {1} were already in the list", added: "{0} links added",
      alreadyListed: "Already in the list", notAdded: "Not added",
      menuLink: "Download with DISO", menuPage: "Download this page with DISO (video)",
      menuSelection: "Download the selected links with DISO",
    },
  };

  // Turkish when the browser speaks Turkish, English otherwise ("tr" when nothing is known, as in the tests).
  function language(nav) {
    const n = nav !== undefined ? nav : (typeof navigator !== "undefined" ? navigator : null);
    const lang = String((n && n.language) || "").toLowerCase();
    return !lang || lang.startsWith("tr") ? "tr" : "en";
  }

  function t(key, args, lang) {
    const texts = TEXTS[lang || language()] || TEXTS.tr;
    const text = key in texts ? texts[key] : TEXTS.tr[key];
    return String(text).replace(/\{(\d)\}/g, (m, i) => String((args || [])[Number(i)]));
  }

  // Puts the texts into a page: <x data-i18n="key"> gets t(key) as its text.
  function translatePage(doc, lang) {
    doc.documentElement.lang = lang || language();
    doc.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n, [], lang); });
    const title = doc.querySelector("title[data-i18n]");
    if (title) doc.title = title.textContent;
  }

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

  function describeResult(r, lang) {
    if (!r) return t("unreachable", [], lang);
    if (r.added && r.duplicates) return t("addedAndDuplicates", [r.added, r.duplicates], lang);
    if (r.added) return t("added", [r.added], lang);
    if (r.duplicates) return t("alreadyListed", [], lang);
    return t("notAdded", [], lang);
  }

  return { APP_ID, DEFAULTS, TEXTS, language, t, translatePage, appBase, isHttpUrl, parseExtensions, fileExtension,
           extractUrls, cookieHeader, shouldIntercept, buildPayload, describeResult };
});
