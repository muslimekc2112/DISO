"""Checks a built DISO for Linux / macOS from the outside (GitHub Actions runs it after tools/build_unix.py).

    python tools/unix/smoke.py <program> <screenshot.png>

1. --selftest: every part the window needs is inside the program (FFmpeg, Deno, the music player ...)
2. the browser's native host: a ping through stdin / stdout, as Chrome does it
3. the window starts, answers on the bridge, registers its native host for the browsers here, downloads a
   file it is given (as the extension gives it), and a screenshot of it is taken
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 17653
TEST_URL = "https://raw.githubusercontent.com/muslimekc2112/DISO/main/LICENSE"
MAC = sys.platform == "darwin"


def fail(text):
    print(f"FAIL: {text}", flush=True)
    sys.exit(1)


def selftest(exe, env):
    out = os.path.join(tempfile.mkdtemp(), "selftest.json")
    subprocess.run([exe, "--selftest", out], env=env, timeout=300, check=True)
    with open(out, encoding="utf-8") as f:
        info = json.load(f)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    for key in ("music_player", "music_ui", "tag_tools", "playable", "extras", "ytmusic"):
        if info.get(key) is not True:
            fail(f"selftest {key}: {info.get(key)}")
    for key in ("ffmpeg", "deno"):
        if not info.get(key) or "error" in str(info.get(key)):
            fail(f"selftest {key}: {info.get(key)}")
    if not info.get("yt_dlp_version") or not info.get("frozen"):
        fail("yt-dlp is not inside the program")


def native_host(exe, env):
    proc = subprocess.Popen([exe, "chrome-extension://adkiobcdpklfjnbajjiocmlifmbhdnei/"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env=env)
    body = json.dumps({"type": "ping"}).encode()
    proc.stdin.write(struct.pack("<I", len(body)) + body)
    proc.stdin.flush()
    head = proc.stdout.read(4)
    if len(head) != 4:
        fail("the native host did not answer")
    reply = json.loads(proc.stdout.read(struct.unpack("<I", head)[0]))
    proc.stdin.close()
    proc.wait(30)
    print("native host:", reply)
    if not (reply.get("ok") and reply.get("app") == "DISO"):
        fail(f"native host answer: {reply}")


def _get(path, method="GET", data=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5) as r:
        return json.loads(r.read().decode())


def window(exe, env, home, shot):
    browsers = (os.path.join(home, "Library", "Application Support", "Google", "Chrome") if MAC
                else os.path.join(home, ".config", "google-chrome"))
    os.makedirs(browsers, exist_ok=True)              # as if Chrome had been used: DISO must register itself there
    proc = subprocess.Popen([exe], env=env)
    try:
        end = time.time() + 120
        while time.time() < end:
            try:
                if _get("/ping").get("app") == "DISO":
                    break
            except Exception:  # noqa: BLE001 - still starting
                pass
            if proc.poll() is not None:
                fail(f"the window closed by itself (exit {proc.returncode})")
            time.sleep(1)
        else:
            fail("the window did not answer on the bridge")
        print("the window is up")
        time.sleep(8)
        if MAC:
            subprocess.run(["screencapture", "-x", shot], timeout=60)
        else:
            from PIL import ImageGrab
            ImageGrab.grab(xdisplay=env.get("DISPLAY")).save(shot)
        print("screenshot:", shot, os.path.exists(shot))
        host = os.path.join(browsers, "NativeMessagingHosts", "com.iso.diso.json")
        end = time.time() + 30
        while not os.path.isfile(host) and time.time() < end:
            time.sleep(1)
        if not os.path.isfile(host):
            fail(f"the native host was not registered in {host}")
        with open(host, encoding="utf-8") as f:
            manifest = json.load(f)
        if os.path.realpath(manifest["path"]) != os.path.realpath(exe):
            fail(f"the native host points elsewhere: {manifest}")
        print("native host registered:", host)
        print("add:", _get("/add", "POST", json.dumps({"urls": [TEST_URL], "kind": "file"}).encode()))
        downloads = os.path.join(home, "Downloads")
        end = time.time() + 120
        found = None
        while time.time() < end and not found:
            time.sleep(2)
            for d, _, names in os.walk(downloads):
                found = next((os.path.join(d, n) for n in names if n.startswith("LICENSE") and not n.endswith(".part")
                              and os.path.getsize(os.path.join(d, n)) > 500), None) or found
        if not found:
            print("status:", _get("/status"))
            for d, _, names in os.walk(home):
                for n in names:
                    print("  ", os.path.join(d, n))
            for d, _, names in os.walk(home):
                for n in names:
                    if n.endswith(".log"):
                        print(open(os.path.join(d, n), encoding="utf-8", errors="replace").read()[-6000:])
            fail(f"the download did not arrive in {downloads}")
        print("downloaded:", found, os.path.getsize(found), "bytes")
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()


def main(argv):
    exe, shot = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    home = tempfile.mkdtemp(prefix="diso-home-")
    os.makedirs(os.path.join(home, "Downloads"))
    env = dict(os.environ, HOME=home, XDG_DATA_HOME="", XDG_CONFIG_HOME="", SDL_AUDIODRIVER="dummy")
    env.pop("XDG_DATA_HOME")
    env.pop("XDG_CONFIG_HOME")
    selftest(exe, env)
    native_host(exe, env)
    window(exe, env, home, shot)
    shutil.rmtree(home, ignore_errors=True)
    print("ALL GOOD")


if __name__ == "__main__":
    main(sys.argv[1:])
