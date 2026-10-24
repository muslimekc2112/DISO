// node --test tests/js/sniff.test.js — sniff.js in a pretend page: answers that start with "#EXTM3U" are told,
// whatever their name; nothing else is, and the page's own requests work as before.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const CODE = fs.readFileSync(path.join(__dirname, "..", "..", "browser_extension", "sniff.js"), "utf8");
const enc = (text) => new TextEncoder().encode(text);

function page(answers) {
  const told = [];
  class XHR {
    constructor() { this.listeners = []; this.responseType = ""; this.status = 200; }
    addEventListener(name, f) { if (name === "load") this.listeners.push(f); }
    open(method, url) { this.url = url; }
    send() {
      const a = answers[this.url];
      this.responseURL = new URL(this.url, "https://site.example/").href;
      if (this.responseType === "arraybuffer") this.response = enc(a).buffer;
      else this.responseText = a;
      this.listeners.forEach((f) => f.call(this));
    }
  }
  const fetchCalls = [];
  const window = {
    location: { href: "https://site.example/watch/1" },
    postMessage: (m) => told.push(m.url),
    fetch: async (url) => {
      fetchCalls.push(url);
      const body = enc(answers[url] || "");
      const make = () => ({
        url: new URL(url, "https://site.example/").href, ok: true,
        headers: { get: () => String(body.length) },
        body: { getReader: () => {
          let done = false;
          return { read: async () => (done ? { done: true } : (done = true, { value: body.slice(0, 8), done: false })),
                   cancel: async () => {} };
        } },
        clone: () => make(),
        text: async () => answers[url],
      });
      return make();
    },
  };
  window.window = window;
  const ctx = vm.createContext({ window, XMLHttpRequest: XHR, URL, location: window.location, TextEncoder });
  vm.runInContext(CODE, ctx);
  return { window, XHR: ctx.XMLHttpRequest, told, fetchCalls };
}

const tick = () => new Promise((r) => setTimeout(r, 20));

test("a playlist behind another name is told, by fetch and by XMLHttpRequest", async () => {
  const p = page({ "/v/list.txt": "#EXTM3U\n#EXT-X-VERSION:3\n", "/v/seg.png": "\x89PNG....", "/v/x.json": "{}",
                   "/v/real.m3u8": "#EXTM3U\n", "/v/bom.txt": "﻿#EXTM3U\n" });
  const r = await p.window.fetch("/v/list.txt");
  assert.equal(await r.text(), "#EXTM3U\n#EXT-X-VERSION:3\n");             // the page gets its answer as always
  await p.window.fetch("/v/x.json");
  await p.window.fetch("/v/real.m3u8");                                      // found by its name already
  const xhr = new p.XHR();
  xhr.open("GET", "/v/seg.png");
  xhr.send();
  const bin = new p.XHR();
  bin.responseType = "arraybuffer";
  bin.open("GET", "/v/list.txt");
  bin.send();
  await tick();
  assert.deepEqual(p.told, ["https://site.example/v/list.txt"]);            // once, only the playlist
  const bom = new p.XHR();
  bom.open("GET", "/v/bom.txt");
  bom.send();
  assert.deepEqual(p.told, ["https://site.example/v/list.txt", "https://site.example/v/bom.txt"]);
});

test("running twice in a page changes nothing", () => {
  const p = page({});
  const before = p.window.fetch;
  vm.runInContext(CODE, vm.createContext({ window: p.window, XMLHttpRequest: p.XHR, URL, location: p.window.location }));
  assert.equal(p.window.fetch, before);
});
