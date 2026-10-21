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
    extensions: "zip,rar,7z,tar,gz,iso,exe,msi,apk,dmg,mp4,mkv,avi,mov,webm,mp3,flac,wav,pdf,torrent",
    badge: true,           // show a short tick on the toolbar button after sending
    launchApp: true,       // start DISO through the native host when it is closed
    torrents: true,        // magnet links and .torrent files always go to DISO (even without "intercept")
    lang: "app",           // "app": the language DISO speaks, or "tr" / "en"
    appLang: "",           // the language DISO told last (kept for when it is closed)
  };

  // Every text the extension shows, in Turkish and English; "{0}", "{1}" are the changing parts.
  const TEXTS = {
    tr: {
      checking: "Kontrol ediliyor…", sendTabVideo: "🎬 MP4 olarak indir (video)", sendTabAudio: "🎵 MP3 olarak indir (ses)",
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
      menuLink: "DISO ile indir", menuPageVideo: "🎬 Bu videoyu DISO ile MP4 indir",
      menuPageAudio: "🎵 Bu videoyu DISO ile MP3 indir",
      menuSelection: "Seçilen bağlantıları DISO ile indir",
      menuTorrents: "🧲 Bu sayfadaki torrentleri DISO ile indir", noTorrents: "Bu sayfada torrent yok",
      torrentsOnPage: "🧲 Bu sayfadaki {0} torrenti indir", torrentOnPage: "🧲 Bu sayfadaki torrenti indir",
      torrentsOption: "Torrentleri her zaman DISO ile indir",
      torrentsHint: "Magnet linkine tıklayınca ya da bir .torrent dosyası inerken DISO devralır; \"Tarayıcı indirmelerini yakala\" kapalı olsa bile.",
      language: "Dil", languageApp: "DISO ile aynı", languageHint: "Eklentinin dili. \"DISO ile aynı\": uygulamada hangi dil seçiliyse.",
      pasteHint: "Link ya da magnet yapıştır…", pasteSend: "⬇ İndir", nothingToSend: "Bunda indirilecek bir link yok",
      moreDownloads: "+{0} indirme daha", waiting: "sırada", magnetSent: "🧲 Torrent DISO'ya gönderildi",
    },
    en: {
      checking: "Checking…", sendTabVideo: "🎬 Download as MP4 (video)", sendTabAudio: "🎵 Download as MP3 (sound)",
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
      menuLink: "Download with DISO", menuPageVideo: "🎬 Download this video as MP4 with DISO",
      menuPageAudio: "🎵 Download this video as MP3 with DISO",
      menuSelection: "Download the selected links with DISO",
      menuTorrents: "🧲 Download the torrents on this page with DISO", noTorrents: "No torrents on this page",
      torrentsOnPage: "🧲 Download the {0} torrents on this page", torrentOnPage: "🧲 Download the torrent on this page",
      torrentsOption: "Always download torrents with DISO",
      torrentsHint: "When you click a magnet link or a .torrent file starts downloading, DISO takes it over; even when \"Catch browser downloads\" is off.",
      language: "Language", languageApp: "Same as DISO", languageHint: "The extension's language. \"Same as DISO\": whichever is chosen in the app.",
      pasteHint: "Paste a link or a magnet…", pasteSend: "⬇ Download", nothingToSend: "There is no link to download in that",
      moreDownloads: "+{0} more downloads", waiting: "queued", magnetSent: "🧲 Torrent sent to DISO",
    },
  };

  // Turkish when the browser speaks Turkish, English otherwise ("tr" when nothing is known, as in the tests).
  function language(nav) {
    const n = nav !== undefined ? nav : (typeof navigator !== "undefined" ? navigator : null);
    const lang = String((n && n.language) || "").toLowerCase();
    return !lang || lang.startsWith("tr") ? "tr" : "en";
  }

  // The language chosen for this page / the background script (setLanguage); null: the browser's.
  let chosen = null;

  // "tr" / "en" from the extension's setting: "app" follows DISO (its last known language), else fixed.
  function pickLanguage(choice, appLanguage, nav) {
    if (choice === "tr" || choice === "en") return choice;
    if (appLanguage === "tr" || appLanguage === "en") return appLanguage;
    return language(nav);
  }

  function setLanguage(code) {
    chosen = code === "tr" || code === "en" ? code : null;
    return chosen;
  }

  function currentLanguage() {
    return chosen || language();
  }

  function t(key, args, lang) {
    const texts = TEXTS[lang || currentLanguage()] || TEXTS.tr;
    const text = key in texts ? texts[key] : TEXTS.tr[key];
    return String(text).replace(/\{(\d)\}/g, (m, i) => String((args || [])[Number(i)]));
  }

  // Puts the texts into a page: <x data-i18n="key"> gets t(key) as its text.
  function translatePage(doc, lang) {
    doc.documentElement.lang = lang || currentLanguage();
    doc.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n, [], lang); });
    doc.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder, [], lang); });
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

  // A magnet link or a link to a .torrent file.
  function isTorrentLink(u) {
    const s = String(u || "");
    if (/^magnet:\?[^\s]+$/i.test(s)) return true;
    if (!isHttpUrl(s)) return false;
    let path = s;
    try { path = decodeURIComponent(new URL(s).pathname); } catch (e) { /* read it as it is */ }
    return fileExtension(path) === "torrent";
  }

  // "magnet:?xt=urn:btih:ABC&dn=x" -> "abc" (the same torrent, whatever else its link says); "" if none
  function magnetHash(u) {
    const m = /[?&]xt=urn:btih:([^&]+)/i.exec(String(u || ""));
    return m ? m[1].toLowerCase() : "";
  }

  // The torrents of a page (magnet links and .torrent files), once each - a magnet once per torrent.
  function pageTorrentLinks(hrefs) {
    const out = [], hashes = new Set();
    (hrefs || []).forEach((h) => {
      const u = String(h || "").trim();
      const link = /^magnet:/i.test(u) ? u : u.split("#")[0];
      if (!isTorrentLink(link) || out.includes(link)) return;
      const hash = magnetHash(link);
      if (hash) {
        if (hashes.has(hash)) return;
        hashes.add(hash);
      }
      out.push(link);
    });
    return out;
  }

  // the app's /status "items" as lines for the popup: name, % done, speed, a torrent mark
  function downloadRows(s, lang) {
    const items = (s && Array.isArray(s.items)) ? s.items : [];
    const rows = items.map((i) => {
      const fraction = Math.max(0, Math.min(1, Number(i.fraction) || 0));
      const detail = i.state === "queued" ? t("waiting", [], lang)
        : Math.round(fraction * 100) + "%" + (i.speed > 0 ? " • " + sizeText(i.speed) + "/s" : "");
      return { name: (i.torrent ? "🧲 " : "") + String(i.name || ""), fraction, detail, queued: i.state === "queued" };
    });
    const busy = (s && (Number(s.active) || 0) + (Number(s.queued) || 0)) || 0;
    return { rows, more: Math.max(0, busy - rows.length) };
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

  // what DISO takes: http(s) links and magnet links (DISO downloads torrents with aria2)
  function isSendable(u) {
    return isHttpUrl(u) || (typeof u === "string" && /^magnet:\?[^\s]+$/i.test(u));
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
    const found = String(text || "").match(/(?:https?:\/\/|magnet:\?)[^\s<>"']+/gi) || [];
    const out = [];
    found.forEach((raw) => {
      let u = raw.replace(/[.,;]+$/, "");
      while (/[)\]]$/.test(u)) {
        const close = u.slice(-1), open = close === ")" ? "(" : "[";
        if (u.split(close).length - 1 > u.split(open).length - 1) u = u.slice(0, -1).replace(/[.,;]+$/, "");
        else break;
      }
      if (isSendable(u) && !out.includes(u)) out.push(u);
    });
    return out;
  }

  // chrome.cookies.getAll() result -> the value of a Cookie header
  function cookieHeader(cookies) {
    return (cookies || []).filter((c) => c && c.name).map((c) => c.name + "=" + c.value).join("; ");
  }

  // How old a download may be and still count as "just started" (ms).
  const FRESH_MS = 60 * 1000;

  // Should the extension take this browser download over? `item` is a chrome DownloadItem.
  // The browser also reports the downloads of its history as "created" (when it starts, when the
  // extension wakes up): those are finished, broken off or old - never taken, only a new one is.
  function shouldIntercept(item, opts, now) {
    if (!opts || !item) return false;
    const torrent = !!opts.torrents && fileExtension(item.filename || item.finalUrl || item.url) === "torrent";
    if (!opts.intercept && !torrent) return false;      // a .torrent file is taken even without "intercept"
    if (item.byExtensionId) return false;              // started by an extension: not ours to take
    if (item.state && item.state !== "in_progress") return false;
    if (item.startTime) {
      const started = Date.parse(item.startTime);
      const t = now !== undefined ? now : Date.now();
      if (!(started > t - FRESH_MS)) return false;     // from the history (or a date we cannot read)
    }
    const url = item.finalUrl || item.url;
    if (!isHttpUrl(url)) return false;                 // blob:, data:, file: ... cannot be fetched again
    const ext = fileExtension(item.filename || url);
    if (torrent) return true;
    if (ext && parseExtensions(opts.extensions).includes(ext)) return true;
    const size = item.fileSize > 0 ? item.fileSize : item.totalBytes > 0 ? item.totalBytes : 0;
    return Number(opts.minSizeMB) > 0 && size >= Number(opts.minSizeMB) * 1024 * 1024;
  }

  // What DISO should make of a link: "file" when its name says it is a file (report.zip, setup.exe,
  // clip.mp4: downloaded as it is, whatever MP3 / MP4 is chosen in the app), "auto" for a page or a
  // stream (DISO looks at it and downloads the video, or the file it turns out to be).
  const PAGE_EXTENSIONS = ["html", "htm", "xhtml", "shtml", "php", "asp", "aspx", "jsp", "cgi", "pl", "m3u8", "mpd"];
  function linkKind(url) {
    if (/^magnet:/i.test(String(url || ""))) return "auto";       // a torrent: DISO knows it by its link
    let path = "";
    try {
      path = new URL(url).pathname;
    } catch (e) {
      return "auto";
    }
    try {
      path = decodeURIComponent(path);
    } catch (e) { /* a broken %-escape: read the name as it is */ }
    const ext = fileExtension(path);
    return /^[a-z0-9]{1,5}$/.test(ext) && !PAGE_EXTENSIONS.includes(ext) ? "file" : "auto";
  }

  // the body of POST /add
  function buildPayload({ urls, referer, userAgent, cookies, kind }) {
    const p = { urls: (urls || []).filter(isSendable) };
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
           extractUrls, cookieHeader, shouldIntercept, buildPayload, describeResult, pageFileLinks, sizeText, statusText,
           linkKind, isSendable, pickLanguage, setLanguage, currentLanguage, isTorrentLink, magnetHash,
           pageTorrentLinks, downloadRows };
});
