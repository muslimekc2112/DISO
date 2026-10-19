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
