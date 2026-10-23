// node --test tests/js/lib.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const HI = require("../../browser_extension/lib.js");

test("appBase uses the port and falls back to the default", () => {
  assert.equal(HI.appBase(17653), "http://127.0.0.1:17653");
  assert.equal(HI.appBase("40000"), "http://127.0.0.1:40000");
  assert.equal(HI.appBase(undefined), "http://127.0.0.1:" + HI.DEFAULTS.port);
});

test("isHttpUrl only accepts http and https links", () => {
  for (const ok of ["http://a.com", "https://a.com/x?y=1#z", "HTTP://A.COM"]) assert.equal(HI.isHttpUrl(ok), true, ok);
  for (const bad of ["ftp://a.com", "blob:https://a.com/1", "data:text/plain,hi", "file:///c:/x", "javascript:alert(1)",
                     "a.com", "", null, undefined, 5, "http://", "https://a b.com"]) assert.equal(HI.isHttpUrl(bad), false, String(bad));
});

test("parseExtensions cleans a typed list", () => {
  assert.deepEqual(HI.parseExtensions("ZIP, .rar ,7z;;iso\n mp4"), ["zip", "rar", "7z", "iso", "mp4"]);
  assert.deepEqual(HI.parseExtensions("zip,zip,ZIP"), ["zip"]);
  assert.deepEqual(HI.parseExtensions(""), []);
  assert.deepEqual(HI.parseExtensions(null), []);
});

test("fileExtension reads names, paths and links", () => {
  assert.equal(HI.fileExtension("movie.MP4"), "mp4");
  assert.equal(HI.fileExtension("C:\\Users\\me\\Downloads\\a.tar.gz"), "gz");
  assert.equal(HI.fileExtension("https://x.com/dl/file.zip?token=1.2#frag"), "zip");
  assert.equal(HI.fileExtension("https://x.com/dl/noext"), "");
  assert.equal(HI.fileExtension(".hidden"), "");
  assert.equal(HI.fileExtension("trailingdot."), "");
  assert.equal(HI.fileExtension(""), "");
  assert.equal(HI.fileExtension(null), "");
});

test("extractUrls finds links in text without repeats and without stray punctuation", () => {
  assert.deepEqual(HI.extractUrls("see https://a.com/x, and http://b.org/y; again https://a.com/x"),
                   ["https://a.com/x", "http://b.org/y"]);
  assert.deepEqual(HI.extractUrls("(bkz https://y.net/z)."), ["https://y.net/z"]);
  assert.deepEqual(HI.extractUrls("https://en.wikipedia.org/wiki/Foo_(bar)"), ["https://en.wikipedia.org/wiki/Foo_(bar)"]);
  assert.deepEqual(HI.extractUrls("[https://y.net/z]"), ["https://y.net/z"]);
  assert.deepEqual(HI.extractUrls("no links"), []);
  assert.deepEqual(HI.extractUrls(null), []);
});

test("cookieHeader joins name=value pairs", () => {
  assert.equal(HI.cookieHeader([{ name: "sid", value: "1" }, { name: "theme", value: "dark" }]), "sid=1; theme=dark");
  assert.equal(HI.cookieHeader([{ name: "", value: "x" }, null, { name: "a", value: "" }]), "a=");
  assert.equal(HI.cookieHeader([]), "");
  assert.equal(HI.cookieHeader(null), "");
});

const on = { intercept: true, minSizeMB: 5, extensions: "zip,iso" };

test("shouldIntercept: switched off, odd links and extension downloads are never taken", () => {
  assert.equal(HI.shouldIntercept({ url: "https://a.com/a.zip" }, { ...on, intercept: false }), false);
  assert.equal(HI.shouldIntercept({ url: "blob:https://a.com/1", filename: "a.zip" }, on), false);
  assert.equal(HI.shouldIntercept({ url: "data:text/plain,x", filename: "a.zip" }, on), false);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/a.zip", byExtensionId: "someone" }, on), false);
  assert.equal(HI.shouldIntercept(null, on), false);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/a.zip" }, null), false);
});

test("shouldIntercept: by file type or by size", () => {
  assert.equal(HI.shouldIntercept({ url: "https://a.com/x", filename: "C:\\dl\\Setup.ISO" }, on), true);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/getfile?id=1", filename: "pack.zip" }, on), true);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/photo.jpg", fileSize: 100 }, on), false);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/photo.jpg", fileSize: 6 * 1048576 }, on), true);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/photo.jpg", totalBytes: 6 * 1048576 }, on), true);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/p.jpg", fileSize: 5 * 1048576 - 1 }, on), false);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/p.jpg", fileSize: -1 }, on), false);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/p.jpg", fileSize: 99 * 1048576 }, { ...on, minSizeMB: 0 }), false);
});

test("shouldIntercept never takes the downloads of the browser's history", () => {
  const now = Date.parse("2026-10-20T12:00:00.000Z");
  const item = (extra) => Object.assign({ url: "https://a.com/a.zip", filename: "a.zip" }, extra);
  const fresh = "2026-10-20T11:59:58.000Z";
  assert.equal(HI.shouldIntercept(item({ state: "in_progress", startTime: fresh }), on, now), true);
  assert.equal(HI.shouldIntercept(item({ state: "complete", startTime: fresh }), on, now), false);
  assert.equal(HI.shouldIntercept(item({ state: "interrupted", startTime: fresh }), on, now), false);
  assert.equal(HI.shouldIntercept(item({ state: "in_progress", startTime: "2026-10-19T09:00:00.000Z" }), on, now), false);
  assert.equal(HI.shouldIntercept(item({ state: "in_progress", startTime: "2026-10-20T11:58:30.000Z" }), on, now), false);
  assert.equal(HI.shouldIntercept(item({ state: "in_progress", startTime: "not a date" }), on, now), false);
});

test("shouldIntercept never takes a download that started before the extension was ready", () => {
  const now = Date.parse("2026-10-22T12:00:00.000Z");
  const item = (startTime) => ({ url: "https://a.com/a.zip", filename: "a.zip", state: "in_progress", startTime });
  const ready = Date.parse("2026-10-22T11:59:50.000Z");          // the extension was added 10 s ago
  assert.equal(HI.shouldIntercept(item("2026-10-22T11:59:55.000Z"), on, now, ready), true);
  assert.equal(HI.shouldIntercept(item("2026-10-22T11:59:48.000Z"), on, now, ready), true);   // it woke the extension
  assert.equal(HI.shouldIntercept(item("2026-10-22T11:59:30.000Z"), on, now, ready), false);  // fresh, but before
  assert.equal(HI.shouldIntercept({ url: "https://a.com/a.zip", filename: "a.zip", state: "in_progress" }, on, now, ready), false);
});

test("shouldIntercept looks at the final address after redirects", () => {
  assert.equal(HI.shouldIntercept({ url: "blob:x", finalUrl: "https://cdn.a.com/f.zip", filename: "" }, on), true);
  assert.equal(HI.shouldIntercept({ url: "https://a.com/go", finalUrl: "ftp://a.com/f.zip" }, on), false);
});

test("buildPayload keeps only what the app understands", () => {
  assert.deepEqual(HI.buildPayload({ urls: ["https://a.com/x", "javascript:1", "ftp://q"], referer: "https://a.com/page",
                                     userAgent: "UA/1", cookies: "sid=1", kind: "video" }),
                   { urls: ["https://a.com/x"], referer: "https://a.com/page", userAgent: "UA/1", cookies: "sid=1", kind: "video" });
  assert.deepEqual(HI.buildPayload({ urls: ["https://a.com/x"], referer: "not a url", kind: "evil" }), { urls: ["https://a.com/x"] });
  assert.deepEqual(HI.buildPayload({}), { urls: [] });
});

test("describeResult explains the app's answer", () => {
  assert.equal(HI.describeResult(null, "tr"), "DISO'ya ulaşılamadı");
  assert.equal(HI.describeResult({ added: 3, duplicates: 0 }, "tr"), "3 bağlantı eklendi");
  assert.equal(HI.describeResult({ added: 1, duplicates: 2 }, "tr"), "1 eklendi, 2 zaten listedeydi");
  assert.equal(HI.describeResult({ added: 0, duplicates: 1 }, "tr"), "Zaten listede");
  assert.equal(HI.describeResult({ added: 0, duplicates: 0 }, "tr"), "Eklenmedi");
  assert.equal(HI.describeResult({ added: 1, duplicates: 2 }, "en"), "1 added, 2 were already in the list");
  assert.equal(HI.describeResult(null, "en"), "Could not reach DISO");
});

test("pageFileLinks keeps the file links of a page, once each", () => {
  const hrefs = ["http://a.com/x.zip", "http://a.com/x.zip#top", "http://a.com/page.html", "https://b.org/v.MP4?s=1",
                 "javascript:void(0)", "mailto:a@b.c", "http://a.com/pic.jpg"];
  assert.deepEqual(HI.pageFileLinks(hrefs, "zip,mp4"), ["http://a.com/x.zip", "https://b.org/v.MP4?s=1"]);
  assert.deepEqual(HI.pageFileLinks([], "zip"), []);
});

test("statusText describes what DISO is doing", () => {
  assert.equal(HI.sizeText(1536 * 1024), "1.5 MB");
  assert.equal(HI.sizeText(500), "500 B");
  assert.equal(HI.statusText({ active: 2, queued: 3, speed: 1536 * 1024 }, "tr"), "⬇ 2 indiriliyor • 1.5 MB/s • 3 sırada");
  assert.equal(HI.statusText({ active: 0, queued: 0, speed: 0 }, "en"), "Nothing is downloading");
  assert.equal(HI.statusText(null, "en"), "Nothing is downloading");
});

test("the language follows the browser: Turkish for Turkish, English for the rest", () => {
  assert.equal(HI.language({ language: "tr-TR" }), "tr");
  assert.equal(HI.language({ language: "en-US" }), "en");
  assert.equal(HI.language({ language: "de" }), "en");
  assert.equal(HI.language({}), "tr");                     // nothing known (the tests' pretend browser)
  assert.equal(HI.t("appRuns", ["0.10.0"], "en"), "DISO is running (v0.10.0)");
});

test("both languages have every text", () => {
  assert.deepEqual(Object.keys(HI.TEXTS.en).sort(), Object.keys(HI.TEXTS.tr).sort());
});

test("the defaults are sane", () => {
  assert.equal(HI.DEFAULTS.port, 17653);
  assert.equal(HI.DEFAULTS.intercept, false);            // taking over downloads is opt-in
  assert.ok(HI.parseExtensions(HI.DEFAULTS.extensions).includes("zip"));
});

test("linkKind: a file's link is a file, a page or a stream is left for DISO to look at", () => {
  for (const u of ["https://a.com/report.zip", "https://a.com/dl/Setup.EXE?x=1", "https://a.com/clip.mp4#t=3",
                   "https://a.com/g%C3%BCzel%20dosya.7z", "https://a.com/a.tar.gz", "https://a.com/song.mp3"]) {
    assert.equal(HI.linkKind(u), "file", u);
  }
  for (const u of ["https://www.youtube.com/watch?v=1", "https://a.com", "https://a.com/", "https://a.com/page.html",
                   "https://a.com/index.php?file=a.zip", "https://a.com/live.m3u8", "https://a.com/v1.2/download",
                   "https://a.com/download", "not a link", "https://a.com/%E0%A4%A.zip?"]) {
    assert.equal(HI.linkKind(u), u.endsWith(".zip?") ? "file" : "auto", u);
  }
});

test("magnet links go to DISO too (it downloads torrents), .torrent files are caught", () => {
  const magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Ubuntu";
  assert.equal(HI.isSendable(magnet), true);
  assert.equal(HI.isSendable("magnet:"), false);
  assert.equal(HI.isHttpUrl(magnet), false);                      // never fetched by the extension itself
  assert.deepEqual(HI.buildPayload({ urls: [magnet, "javascript:1"] }), { urls: [magnet] });
  assert.deepEqual(HI.extractUrls(`indir: ${magnet} ve https://a.com/b.`), [magnet, "https://a.com/b"]);
  assert.equal(HI.linkKind(magnet), "auto");
  assert.ok(HI.parseExtensions(HI.DEFAULTS.extensions).includes("torrent"));
});

test("the language: chosen in the settings, else DISO's, else the browser's", () => {
  assert.equal(HI.pickLanguage("en", "tr"), "en");
  assert.equal(HI.pickLanguage("tr", "en"), "tr");
  assert.equal(HI.pickLanguage("app", "en"), "en");
  assert.equal(HI.pickLanguage("app", "", { language: "de-DE" }), "en");
  assert.equal(HI.pickLanguage("app", "", { language: "tr-TR" }), "tr");
  try {
    HI.setLanguage("en");
    assert.equal(HI.t("settings"), "⚙ Settings");
    assert.equal(HI.currentLanguage(), "en");
    assert.equal(HI.t("settings", [], "tr"), "⚙ Ayarlar");          // asked for by name: that one
    HI.setLanguage("xx");                                            // nonsense: back to the browser's
    assert.equal(HI.t("settings"), "⚙ Ayarlar");
  } finally {
    HI.setLanguage(null);
  }
});

test("every text exists in both languages", () => {
  assert.deepEqual(Object.keys(HI.TEXTS.tr).sort(), Object.keys(HI.TEXTS.en).sort());
});

test("torrents of a page: magnets once per torrent, .torrent files once, nothing else", () => {
  const hrefs = ["magnet:?xt=urn:btih:ABCDEF&dn=a", "magnet:?xt=urn:btih:abcdef&dn=b&tr=x", "http://x.org/a.torrent#top",
                 "http://x.org/a.torrent", "http://x.org/a.zip", "https://x.org/%C3%A7ok%20iyi.torrent", "magnet:",
                 "http://x.org/torrent", "javascript:void(0)", "magnet:?xt=urn:btih:99"];
  assert.deepEqual(HI.pageTorrentLinks(hrefs), ["magnet:?xt=urn:btih:ABCDEF&dn=a", "http://x.org/a.torrent",
                                                "https://x.org/%C3%A7ok%20iyi.torrent", "magnet:?xt=urn:btih:99"]);
  assert.equal(HI.magnetHash("magnet:?dn=x&xt=urn:btih:AbC"), "abc");
  assert.equal(HI.isTorrentLink("http://x.org/a.TORRENT?dl=1"), true);
  assert.equal(HI.isTorrentLink("http://x.org/a.torrent.zip"), false);
});

test("a .torrent file is always taken (unless switched off), even without intercept", () => {
  const now = Date.now();
  const item = { url: "http://x.org/get?id=1", filename: "C:\\dl\\ubuntu.torrent", fileSize: 20000, state: "in_progress",
                 startTime: new Date(now).toISOString() };
  assert.equal(HI.shouldIntercept(item, { intercept: false, torrents: true }, now), true);
  assert.equal(HI.shouldIntercept(item, { intercept: false, torrents: false }, now), false);
  assert.equal(HI.shouldIntercept(Object.assign({}, item, { state: "complete" }), { torrents: true }, now), false);
  assert.equal(HI.shouldIntercept({ url: "http://x.org/a.zip", filename: "a.zip", fileSize: 10 },
                                  { intercept: false, torrents: true }, now), false);
  assert.equal(HI.DEFAULTS.torrents, true);
});

test("the popup's download lines", () => {
  const s = { active: 2, queued: 5, items: [
    { name: "Ubuntu", fraction: 0.456, speed: 2 * 1048576, state: "active", torrent: true },
    { name: "film.mp4", fraction: 2, speed: 0, state: "active", torrent: false },
    { name: "next.zip", fraction: 0, speed: 0, state: "queued", torrent: false }] };
  const { rows, more } = HI.downloadRows(s, "en");
  assert.deepEqual(rows.map((r) => [r.name, r.detail, r.queued]),
                   [["🧲 Ubuntu", "46% • 2.0 MB/s", false], ["film.mp4", "100%", false], ["next.zip", "queued", true]]);
  assert.equal(rows[1].fraction, 1);
  assert.equal(more, 4);
  assert.deepEqual(HI.downloadRows(null), { rows: [], more: 0 });
});

// ------------------------------------------------------------------ 🎞 videos a page plays
test("mediaKind tells streams, files and subtitles from the pieces and the rest", () => {
  assert.equal(HI.mediaKind("https://a.com/x/master.m3u8?t=1"), "hls");
  assert.equal(HI.mediaKind("https://a.com/play", "application/vnd.apple.mpegurl; charset=utf-8"), "hls");
  assert.equal(HI.mediaKind("https://a.com/x/stream.mpd"), "dash");
  assert.equal(HI.mediaKind("https://a.com/movie.mp4", "video/mp4", 50e6), "video");
  assert.equal(HI.mediaKind("https://a.com/get?id=1", "video/mp4", 0), "video");           // size not told: kept
  assert.equal(HI.mediaKind("https://a.com/song.mp3", "audio/mpeg", 4e6), "audio");
  assert.equal(HI.mediaKind("https://a.com/subs/tr.vtt"), "subtitle");
  assert.equal(HI.mediaKind("https://a.com/subs/x", "text/vtt"), "subtitle");
  for (const [u, ct, size] of [["https://a.com/seg-1.ts", "video/mp2t", 9e5], ["https://a.com/c-2.m4s", "video/mp4", 9e5],
                               ["https://a.com/ad.mp4", "video/mp4", 3000], ["https://a.com/p.jpg", "image/jpeg", 9e5],
                               ["https://a.com/page", "text/html", 9e5], ["blob:https://a.com/1", "video/mp4", 9e6]]) {
    assert.equal(HI.mediaKind(u, ct, size), null, u);
  }
});

test("the size of a whole file is read from a range answer too", () => {
  assert.equal(HI.responseSize([{ name: "Content-Range", value: "bytes 0-999/123456789" }, { name: "Content-Length", value: "1000" }]), 123456789);
  assert.equal(HI.responseSize([{ name: "content-length", value: "5000" }]), 5000);
  assert.equal(HI.responseSize([]), 0);
  assert.equal(HI.headerValue([{ name: "REFERER", value: "http://x" }], "referer"), "http://x");
  assert.equal(HI.headerValue(null, "referer"), "");
});

test("a subtitle's language and a stream's quality come from their address", () => {
  assert.equal(HI.subtitleLanguage("https://x.com/subs/Turkce.vtt"), "tr");
  assert.equal(HI.subtitleLanguage("https://x.com/s?lang=en&f=1.vtt"), "en");
  assert.equal(HI.subtitleLanguage("https://x.com/s/123.vtt"), "");
  assert.equal(HI.qualityOf("https://x.com/hls/1080p/index.m3u8"), 1080);
  assert.equal(HI.qualityOf("https://x.com/v_720.m3u8?t=2160"), 720);                      // not the query
  assert.equal(HI.qualityOf("https://x.com/a.m3u8"), 0);
});

test("found videos are ranked (whole playlists and the best first) and kept once", () => {
  const list = [];
  assert.equal(HI.addFound(list, { url: "u1", kind: "video", size: 5e6 }), true);
  assert.equal(HI.addFound(list, { url: "u1", kind: "video" }), false);
  for (let i = 0; i < 50; i++) HI.addFound(list, { url: "x" + i, kind: "audio" }, 10);
  assert.equal(list.length, 10);
  const ranked = HI.rankMedia([{ url: "https://a/720/index.m3u8", kind: "hls" }, { url: "https://a/f.mp4", kind: "video", size: 9 },
                               { url: "https://a/master.m3u8", kind: "hls" }, { url: "https://a/1080/index.m3u8", kind: "hls" },
                               { url: "https://a/s.mp3", kind: "audio" }]);
  assert.deepEqual(ranked.map((e) => e.url), ["https://a/master.m3u8", "https://a/1080/index.m3u8", "https://a/720/index.m3u8",
                                              "https://a/f.mp4", "https://a/s.mp3"]);
  assert.equal(HI.mediaLine({ kind: "hls", url: "https://cdn.x.com/1080/index.m3u8" }, "tr"), "Akış (HLS) • 1080p • cdn.x.com");
  assert.equal(HI.mediaLine({ kind: "video", url: "https://x.com/a.mp4", size: 1536000 }, "en"), "Video file • 1.5 MB • x.com");
});

test("the payload for found videos carries the player's headers, names, quality and subtitles", () => {
  const p = HI.buildMediaPayload([{ url: "https://cdn/a.m3u8", referer: "https://player/e/1", origin: "https://player", cookies: "a=1" },
                                  { url: "https://cdn/b.mp4" }, { url: "blob:x" }],
                                 { kind: "video", quality: "720p", title: "  Film   Adı ", subs: [{ url: "https://cdn/tr.vtt", lang: "tr" }],
                                   userAgent: "UA" });
  assert.equal(p.kind, "video");
  assert.equal(p.quality, "720p");
  assert.deepEqual(p.media.map((m) => m.title), ["Film Adı (1)", "Film Adı (2)"]);
  assert.deepEqual(p.media[0], { url: "https://cdn/a.m3u8", title: "Film Adı (1)", referer: "https://player/e/1", userAgent: "UA",
                                 cookies: "a=1", headers: { Origin: "https://player" },
                                 subs: [{ url: "https://cdn/tr.vtt", lang: "tr", ext: "vtt" }] });
  assert.equal(HI.buildMediaPayload([{ url: "https://cdn/a.mp3" }], { kind: "audio", quality: "En iyi" }).quality, undefined);
  assert.deepEqual(HI.mediaTitles("", 1), ["video"]);
  const alts = HI.alternatesOf([{ url: "https://a/s.mp3", kind: "audio" }, { url: "https://a/x.m3u8", kind: "hls", referer: "https://p/" }], "UA");
  assert.deepEqual(alts, [{ url: "https://a/x.m3u8", referer: "https://p/", userAgent: "UA" }]);
  assert.equal(HI.badgeCount(0), "");
  assert.equal(HI.badgeCount(3), "3");
  assert.equal(HI.badgeCount(12), "9+");
});

test("every new text is there in both languages", () => {
  for (const key of ["foundTitle", "foundNone", "foundCount", "sendFoundVideo", "sendFoundAudio", "withSubs", "kindHls",
                     "sniffOption", "sniffHint", "menuFound", "sentFound", "nothingChosen", "qualityLabel"]) {
    assert.ok(HI.TEXTS.tr[key] && HI.TEXTS.en[key], key);
  }
});
