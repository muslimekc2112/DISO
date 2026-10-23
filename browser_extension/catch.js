// Runs in every page: a click on a magnet link goes to DISO (when "Always download torrents with DISO"
// is on). If DISO cannot take it, the click goes on and the browser opens the link as it would anyway.
(function () {
  "use strict";
  const api = typeof chrome !== "undefined" && chrome.runtime ? chrome : browser;
  let passing = null;            // a magnet given back to the browser: not caught a second time

  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || !/^magnet:\?/i.test(a.href)) return;
    if (a.href === passing) { passing = null; return; }
    e.preventDefault();
    const href = a.href;
    try {
      api.runtime.sendMessage({ type: "magnet", url: href, referer: location.href }, (r) => {
        void api.runtime.lastError;              // no answer (the extension was reloaded): read so it is not reported
        if (r && r.ok) return;
        passing = href;
        a.click();
      });
    } catch (err) {                              // the extension is gone from this page (updated, removed)
      passing = href;
      a.click();
    }
  }, true);

  // 🎞 a playlist hidden behind another name, found by sniff.js (which runs in the page itself)
  window.addEventListener("message", (e) => {
    const d = e.data;
    if (e.source !== window || !d || d.__diso !== "stream" || typeof d.url !== "string" || !/^https?:\/\//i.test(d.url)) return;
    try {
      api.runtime.sendMessage({ type: "stream", url: d.url }, () => void api.runtime.lastError);
    } catch (err) { /* the extension is gone from this page */ }
  });
})();
