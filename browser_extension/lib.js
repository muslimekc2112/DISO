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
    launchApp: true,       // start DISO through the native host when it is closed
  };

  // Every text the extension shows, in Turkish and English; "{0}", "{1}" are the changing parts.
  const TEXTS = {
    tr: {
      checking: "Kontrol ediliyor…", sendTab: "⬇ Bu sekmeyi indir", sendTabAudio: "🎵 Bu sekmeyi MP3 olarak indir",
      catchDownloads: "Tarayıcı indirmelerini yakala", settings: "⚙ Ayarlar",
      appRuns: "DISO çalışıyor (v{0})", appClosed: "DISO kapalı — bir şey indirince kendisi açılır", noAnswer: "Cevap yok",
      openApp: "▶ DISO'yu aç", opening: "DISO açılıyor…", openFailed: "DISO açılamadı. DISO'yu bir kez kendin aç; sonra eklenti onu kapalıyken de açabilir.",
      launchOption: "DISO kapalıysa aç", launchHint: "Bir şey indirmek istediğinde DISO kapalıysa eklenti onu kendisi açar.",
      busy: "⬇ {0} indiriliyor • {1}/s", queuedToo: " • {0} sırada", idle: "Şu an indirme yok",
      menuAllLinks: "Bu sayfadaki tüm dosya linklerini DISO ile indir", noFileLinks: "Bu sayfada indirilecek dosya linki yok",
      optionsTitle: "DISO — Ayarlar", port: "Bağlantı noktası",
      portHint: "Uygulamadaki Ayarlar → \"Eklenti bağlantı noktası\" ile aynı olmalı.",
      redirect: "Tarayıcı indirmelerini DISO'ya yönlendir",
      redirectHint: "DISO kapalıysa ve açılamıyorsa indirme tarayıcıda normal şekilde devam eder.",
      minSize: "En az boyut (MB)", minSizeHint: "Bu boyuttan büyük indirmeler yakalanır. 0: yalnızca aşağıdaki dosya türleri.",
      types: "Her zaman yakalanacak dosya türleri", badge: "Gönderince araç çubuğu simgesinde ✓ göster",
      save: "Kaydet", test: "Bağlantıyı dene", badPort: "Port 1024 ile 65535 arasında bir sayı olsun.", saved: "Kaydedildi.",
      connected: "✓ Uygulamaya bağlanıldı (v{0})", otherApp: "Bu portta başka bir şey çalışıyor.",
      unreachableLong: "Uygulamaya ulaşılamadı. DISO açık mı, port doğru mu?",
      unreachable: "DISO'ya ulaşılamadı", unreachableOpen: "DISO'ya ulaşılamadı: DISO açık mı? (Bir kez kendin açarsan sonra eklenti onu kendisi açabilir.)",
      bridgeOff: "Uygulamada tarayıcı eklentisi kapalı", refused: "Uygulama reddetti: {0}",
      addedAndDuplicates: "{0} eklendi, {1} zaten listedeydi", added: "{0} bağlantı eklendi",
      alreadyListed: "Zaten listede", notAdded: "Eklenmedi",
      menuLink: "DISO ile indir", menuPage: "Bu sayfayı DISO ile indir (video)",
      menuSelection: "Seçilen bağlantıları DISO ile indir",
    },
    en: {
      checking: "Checking…", sendTab: "⬇ Download this tab", sendTabAudio: "🎵 Download this tab as MP3",
      catchDownloads: "Catch browser downloads", settings: "⚙ Settings",
      appRuns: "DISO is running (v{0})", appClosed: "DISO is closed — it opens by itself when you download", noAnswer: "No answer",
      openApp: "▶ Open DISO", opening: "Opening DISO…", openFailed: "Could not open DISO. Open DISO yourself once; after that the extension can open it while it is closed.",
      launchOption: "Open DISO when it is closed", launchHint: "When you want to download something and DISO is closed, the extension opens it for you.",
      busy: "⬇ {0} downloading • {1}/s", queuedToo: " • {0} queued", idle: "Nothing is downloading",
      menuAllLinks: "Download all file links on this page with DISO", noFileLinks: "No file links to download on this page",
      optionsTitle: "DISO — Settings", port: "Port",
      portHint: "Must be the same as Settings → \"Extension port\" in the app.",
      redirect: "Send browser downloads to DISO",
      redirectHint: "If DISO is closed and cannot be opened, the download goes on in the browser as usual.",
      minSize: "Minimum size (MB)", minSizeHint: "Downloads bigger than this are caught. 0: only the file types below.",
      types: "File types that are always caught", badge: "Show ✓ on the toolbar button after sending",
      save: "Save", test: "Test the connection", badPort: "The port must be a number from 1024 to 65535.", saved: "Saved.",
      connected: "✓ Connected to the app (v{0})", otherApp: "Something else is running on this port.",
      unreachableLong: "Could not reach the app. Is DISO open, is the port right?",
      unreachable: "Could not reach DISO", unreachableOpen: "Could not reach DISO: is it open? (Open it yourself once; after that the extension can open it by itself.)",
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

  // The links of a page that point at files of the given types (like IDM's "download all links"), once each.
  function pageFileLinks(hrefs, extensions) {
    const wanted = parseExtensions(extensions);
    const out = [];
    (hrefs || []).forEach((h) => {
      const u = String(h || "").split("#")[0];
      if (isHttpUrl(u) && wanted.includes(fileExtension(u)) && !out.includes(u)) out.push(u);
    });
    return out;
  }

  // 1536000 -> "1.5 MB"
  function sizeText(bytes) {
    let n = Number(bytes) || 0;
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? String(Math.round(n)) : n.toFixed(1)) + " " + units[i];
  }

  // the app's /status as one line for the popup
  function statusText(s, lang) {
    if (!s || !(s.active > 0)) return t("idle", [], lang) + (s && s.queued > 0 ? t("queuedToo", [s.queued], lang) : "");
    return t("busy", [s.active, sizeText(s.speed)], lang) + (s.queued > 0 ? t("queuedToo", [s.queued], lang) : "");
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

  const HOST = "com.iso.diso";       // the native host (app/native_host.py) that starts DISO when it is closed

  return { APP_ID, HOST, DEFAULTS, TEXTS, language, t, translatePage, appBase, isHttpUrl, parseExtensions, fileExtension,
           extractUrls, cookieHeader, shouldIntercept, buildPayload, describeResult, pageFileLinks, sizeText, statusText };
});
