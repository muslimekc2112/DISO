// Runs inside the page itself (every frame, before the page's own scripts): some sites hide their video's
// playlist behind another name (".txt", ".png", no extension at all). The page's own requests are watched
// (only watched: nothing is changed) and the first bytes of each answer are looked at; an answer that starts
// with "#EXTM3U" is a video playlist whatever it is called. Its address goes to catch.js (and from there to
// the extension). Nothing else of the page is read or sent.
(function () {
  "use strict";
  if (window.__disoSniff) return;
  window.__disoSniff = true;
  const told = new Set();
  const MARK = "#EXTM3U";

  function tell(url) {
    try {
      url = new URL(url, location.href).href;
    } catch (e) {
      return;
    }
    if (!/^https?:/i.test(url) || told.has(url)) return;
    told.add(url);
    window.postMessage({ __diso: "stream", url }, "*");
  }

  function startsWithMark(bytes) {
    if (!bytes || bytes.length < MARK.length) return false;
    let i = bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf ? 3 : bytes[0] === 0xfeff ? 1 : 0;   // (a byte order mark)
    for (const ch of MARK) {
      if (bytes[i++] !== ch.charCodeAt(0)) return false;
    }
    return true;
  }

  function plainName(url) {                     // a ".m3u8" is found by its name already: not read again
    return !/\.m3u8?(\?|#|$)/i.test(String(url || ""));
  }

  // fetch(): a copy of the answer is read, only its first piece
  const realFetch = window.fetch;
  if (typeof realFetch === "function") {
    window.fetch = function (input, init) {
      const promise = realFetch.apply(this, arguments);
      promise.then((resp) => {
        try {
          const url = resp.url || (input && input.url) || String(input);
          const size = Number(resp.headers.get("content-length")) || 0;
          if (!resp.ok || !resp.body || !plainName(url) || size > 4 * 1024 * 1024) return;
          const reader = resp.clone().body.getReader();
          reader.read().then(({ value }) => {
            reader.cancel().catch(() => {});
            if (startsWithMark(value)) tell(url);
          }).catch(() => {});
        } catch (e) { /* the page goes on as always */ }
      }).catch(() => {});
      return promise;
    };
  }

  // XMLHttpRequest (hls.js and most players): looked at when it has loaded
  const realOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    try {
      this.__disoUrl = url;
      this.addEventListener("load", function () {
        try {
          const where = this.responseURL || this.__disoUrl;
          if (!plainName(where) || this.status >= 400) return;
          let first = null;
          if (this.responseType === "" || this.responseType === "text") {
            const text = String(this.responseText || "").slice(0, 16);
            first = Array.from(text, (c) => c.charCodeAt(0));
          } else if (this.responseType === "arraybuffer" && this.response) {
            first = new Uint8Array(this.response, 0, Math.min(16, this.response.byteLength));
          }
          if (startsWithMark(first)) tell(where);
        } catch (e) { /* the page goes on as always */ }
      });
    } catch (e) { /* the page goes on as always */ }
    return realOpen.apply(this, arguments);
  };
})();
