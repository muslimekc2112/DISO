# DISO

**English | [Türkçe](README.tr.md)**

A download manager for files, videos and music, with a music player built in. For Windows. **Version 0.11.1 beta**: everything works, but some corners may still be rough. The interface speaks **English and Turkish**.

Paste a link and leave the rest to DISO: **files** (split into parts over many connections, like IDM/FDM), **video (MP4)**, **MP3**, YouTube / Instagram / TikTok / X and more.

## Installing (on a PC without Python)
Double-click `DISO-Setup-0.11.1-beta.exe` and press **Install**. Python, FFmpeg, yt-dlp and the Deno that YouTube needs are all inside the package; there is nothing else to install.
- **It asks for administrator rights:** DISO is installed for everyone on the PC, in `C:\Program Files\ISO\DISO`. Windows asks "allow?"; say **Yes**.
- It adds Start menu and desktop shortcuts and appears in the "Apps" list. If you like, it starts together with Windows.
- It asks **which browsers should get the extension** (right-click a link → "Download with DISO", like IDM) and helps you add it; see [Browser extension](#-browser-extension).
- **Updating:** just run the new setup file. It closes a running DISO and installs into the same folder; your settings and playlists stay.
- **Coming from the old version** (Hızlı İndirici): setup removes the old one itself and moves your settings, playlists and download list to `%LOCALAPPDATA%\DISO`. Nothing is lost.
- **Uninstalling:** Settings → Apps → DISO → Uninstall (or "Uninstall DISO" in the Start menu). Only what setup put there is deleted. It asks whether your settings, playlists and the songs you found and downloaded in the music player should go too. What you downloaded to your download folder is never touched.
- **Silent install:** `DISO-Setup-0.11.1-beta.exe --silent [--dir "C:\path"] [--no-desktop] [--autostart]` and `Uninstall.exe --silent [--remove-data]`. Log: `%TEMP%\DISO-kurulum.log`.
- Windows may warn about an "unknown publisher" (the package is not digitally signed): **More info → Run anyway**.

## 🌐 Language
DISO, its installer and its browser extension speak **English and Turkish**. On the first start DISO uses Turkish if Windows is in Turkish, and English otherwise. You can switch at any time: Settings → **Language** (DISO restarts). The setup and uninstall windows use the language you chose in DISO; the browser extension uses the browser's language.

## For developers
1. Install Python 3.10+ (tick **"Add Python to PATH"** in its installer).
2. Double-click `run.bat`: it installs the libraries and starts the program. (By hand: `pip install -r requirements.txt`, then `python main.py`)
3. `build.bat` makes a portable single-file `DISO.exe` that needs no install (`build.bat --no-ffmpeg` for a smaller one). It unpacks itself to a temporary folder at every start, so it takes a few seconds to open.
4. `python tools/build_installer.py` makes the setup package: it builds the program as a folder (`build\app\DISO`, `python tools/build_exe.py --onedir`), downloads Deno and checks its SHA-256, and writes `dist\DISO-Setup-<version>.exe`. The installed DISO is a folder, so it opens in 2–3 seconds.
5. The icons are made from one picture: after changing `IKON\icon.png`, run `python tools/make_icons.py`.

The name, publisher, version and GitHub address are written in one place: `app/brand.py`. The program's texts are written in Turkish; their English is in `app/lang_en.py` (the keys are the Turkish texts as shown on screen).

**No need to install FFmpeg:** the first time an MP3 or a video+audio merge needs it, DISO downloads it itself (once, ~115 MB, checked with SHA-256). If you prefer, put `ffmpeg.exe` and `ffprobe.exe` into the `ffmpeg/` folder.

## Using it
- Paste a link and press **⬇ Download**. In "Automatic" mode DISO works out by itself whether it is a file or a video.
- `📄` adds every link in a `.txt` file, and `Ctrl+V` puts the links on the clipboard into the list. A link already in the list is not added again.
- The **ℹ** button shows a link's qualities, sizes and subtitle languages; download the quality you want, or MP3, with one click.
- With **Playlist** ticked, adding a playlist link lets you choose which videos to download.
- The **subtitles** menu (Turkish / English / all languages) saves subtitles as `.srt` next to the video and also puts them inside the MP4 (players offer them as a subtitle track). YouTube sometimes refuses its own translation (e.g. English to Turkish); then the subtitles in the video's own language are saved and the row says so. The video is always downloaded, even when the subtitles are not. MP3s get the video's thumbnail embedded as **cover art**.
- **Folders by type** sorts files into Video, Music, Archives, Documents, Programs, Images and Other folders.
- Every row has ⏸/▶ (pause/resume), 📂 (open folder) and ✖ (remove), plus a **right-click** menu and double-click to open. Unfinished downloads go on from where they stopped, even after DISO was closed. The coloured strip on the left of a row shows its state (downloading, done, error, paused).
- The list has search, filters, sorting and checkboxes for picking several rows (start/pause/delete them together). Shortcuts: `Ctrl+F` search, `Ctrl+A` select all, `Delete` delete the selected ones.
- If the connection drops, the download **retries by itself** (after 10, 30, 60 s… growing waits) and goes on from where it stopped.
- A sound and a Windows notification tell you when a download is done.

### 🎵 Music player mode
The **Download mode | Music player mode** switch at the bottom of the window opens a separate music player window. Downloads go on in the background, and the music keeps playing when you switch windows.
- Make **as many playlists as you like** (`＋` new, `✎` rename, `🗑` delete). They survive closing DISO (`%LOCALAPPDATA%\DISO\playlists.json`).
- Add music with `＋ File` and `📁 Folder`, put the songs in any order with `▲` `▼` (or `Ctrl+↑/↓`), take them out with `Delete`. The files themselves are never deleted.
- Double-click a song to start from it. There is play/pause, previous/next, a progress bar, volume, **🔀 Shuffle** and **🔁 Repeat** (off / list / one song). `Space` plays/pauses.
- The song table shows **artist, title and length** (read from the file's tags in the background; a file without tags shows its file name). The list's total length is shown below it. The playing song's **cover art** and album appear in the player box.
- Finished music downloads **go into a playlist by themselves**: a YouTube playlist into a list with its own name (in its order), a single MP3 into the "Downloaded" list. To turn this off: Settings → "Put finished music into a playlist". From a download's **right-click menu → Add to a playlist** you can also put it into any list.
- **A song whose file was deleted leaves the list by itself** (a short note says so). A song on a USB stick that is not plugged in does not count as deleted; it is still there when the stick comes back.
- **Search the list** (`Ctrl+F`): filters as you type. **Click a column title** to sort by that column (click again for reverse).
- **Right-click:** play, show in folder, add to another list, remove from the list.
- **Go on where you left off:** after restarting DISO the last song shows as "Where you left off", and ▶ goes on from the same second.
- **⏭ Play next / ➕ Add to queue** (right-click): plays the songs you pick after the current one without changing the list; the **📋 Queue** button shows the queue (click to remove one, or clear them all).
- **🎚 Crossfade** (⚙ menu): while a song fades out the next one fades in over 3, 6 or 10 seconds.
- **🗗 Mini player**: a small always-on-top player in the corner (cover, ⏮ ⏯ ⏭, progress); ⤢ goes back to the big window.
- **Taskbar and the Windows media panel**: ⏮ ⏯ ⏭ in the music window's taskbar preview; the panel Windows shows when you press the volume keys shows the song, artist and cover, with its buttons.
- The **🔀 Shuffle** button gives the list a new random order for good (`Ctrl+Z` brings the old order back if you don't like it). To listen in random order without changing the list, use the **🔀 Shuffle** box in the player.
- **🎤 Lyrics:** when the playing (or selected) song has lyrics, a **🎤 Lyrics** button appears at the top right of the player; otherwise it is not shown. In the lyrics window timed lyrics scroll with the song: the line being sung is big and coloured, clicking a line jumps there, and A−/A+ change the text size. Lyrics come from **YouTube Music** first (for a song downloaded by DISO, that very video's lyrics; for others a search by title and artist); when YouTube Music has no line timings, they come from [LRCLIB](https://lrclib.net), but only if the text is the same song. They are saved next to the song as `song.lrc`. If they are wrong: right-click → "🔄 Wrong lyrics, look again", or "Wrong? Look again" in the lyrics window. Songs downloaded with "Find songs" get their lyrics looked up by themselves; for other songs, right-click → "Find lyrics online".
- **😴 Sleep timer:** stops the music after 15–90 minutes, or when the current song ends.
- **The media keys on your keyboard** (play/pause, next, previous, stop) work whether DISO is in front or not. DISO only takes them while music is playing (or paused); once stopped, it gives them back to the browser and other programs.
- Supported formats are the ones Windows can play: mp3, wav, wma, m4a, aac. For files Windows cannot open directly (MP3s with large cover art, videos with Opus sound) a playable copy is made in the background the first time they play.

#### 🔍 Find songs
Type a song or artist name (or a YouTube link) in the **🔍 Find songs** tab at the top of the music player and press Enter. The results show title, channel and length.
- **Double-click** the one you like, or select it and press **⬇ Download (MP3)**. The song downloads in the background as an MP3 (with cover art) while you keep listening. Only its percentage is shown.
- When it's done DISO asks **which list it should go into**: an existing list, a new list or "Not now". Songs that finish together get one question; the list you chose last is offered first next time.
- Songs you find and download are kept in `%LOCALAPPDATA%\DISO\Müzik` (the **📂 Downloaded** button opens it). They also show in the download list, where you can pause and resume them.
- **🎧 Preview**: listen to 30 seconds of a song before downloading (the music that was playing waits, then goes on).
- While you type, **YouTube suggestions** and **your recent searches** appear; pick one with ↑ ↓ and Enter.
- Paste a **YouTube Music / YouTube playlist link** to get its songs; **⬇ Download all** downloads them all as MP3 into a playlist with the list's name, in order.
- The same song is never downloaded twice: if it is downloading DISO waits, if it is done it asks whether to add it to a list again, and if it stopped halfway it goes on from there.

### ⚙ Settings
Number of downloads at the same time (1–8), a total **speed limit**, the number of automatic retries, a **proxy** (http / socks5, with a "Test" button), notifications, the **scheduler**, **keep running when closed** (system tray), **start with Windows**, theme (dark/light/system), style (New/Classic), **language** (Türkçe/English), what to do "when all downloads finish" (close DISO / sleep / shut down the PC) and the log file. Everything you choose is remembered.

**Backup and help:** 💾 Back up (settings, playlists, download list and history in one `.disoyedek` file), 📂 Restore (bring them from another PC), 📊 Download history (what was downloaded when, how fast, from which sites the most; rows you removed from the list stay here), ⌨ Keyboard shortcuts (**F1** everywhere).

**ℹ About** (in Settings, or click the BETA badge in the title): shows the version, where DISO is installed and where its data is. **📋 Copy details** puts the version, Windows, yt-dlp, FFmpeg and Deno details on the clipboard in one go, and **✉ Contact us** opens a new issue page on GitHub.

### ⏰ Scheduler (downloading at night)
Turn on Settings → Scheduler and type the start time (and, if you like, the end time), for example `02:00`–`07:00`. New downloads wait in the queue until the start time. At the end time the running ones pause and go on at the next start time.

## 🧩 Browser extension
DISO has a browser extension for **Chrome, Edge, Brave, Opera, Vivaldi** (and Firefox, see below), like IDM's:
- **Right-click a link → "Download with DISO"**: the download starts in DISO at once. Also on a video / sound / picture, on selected text (every link in it), and **"Download all file links on this page with DISO"** (only links to file types such as zip, exe, mp4, mp3, pdf … — the list is in the extension's settings).
- **DISO opens by itself when it is closed.** The extension starts it (through the browser's "native messaging", the way IDM does it), waits until it is ready and hands the link over. No need to keep DISO running.
- **Catching the browser's own downloads** (optional, in the extension's settings): files of the chosen types or above a size go to DISO instead. While DISO is starting the browser's download waits; if DISO cannot start, the browser simply goes on.
- The toolbar button shows whether DISO runs, **what it is downloading right now** (count and speed), and has **▶ Open DISO**, "download this tab" and "download this tab as MP3".
- For sites that need a login, the browser's session (cookies, page address) is passed along; cookies are never written to disk. DISO listens only on this PC and accepts requests only from the **extension**, never from web pages.
- English or Turkish, following the browser's language.

**Adding it to your browser:** if the extension is not in a browser yet, DISO asks once after it starts: "Shall we add DISO to your browser?" (**Add the extension** / **Remind me later** — in three days / **Don't ask again**); once the extension has talked to DISO it never asks again. Setup also asks **which browsers** should get the extension (the ones on your PC are ticked) and at the end opens a short guide; later the same guide is in DISO: Settings → **🧩 Add to browser**. Browsers only install extensions from their stores by themselves, so it takes three clicks: the guide opens the browser's extensions page and the extension's folder and copies the folder's path; turn on **Developer mode**, press **Load unpacked**, paste the path (`Ctrl+V`) and press **Select Folder** (or drag the folder onto the page). The folder is `C:\Program Files\ISO\DISO\browser_extension` (a portable `DISO.exe` keeps it in `%LOCALAPPDATA%\DISO\browser_extension`). Updates of DISO update the extension in the same folder; the browser picks them up after a restart.

**Firefox:** on `about:debugging` → "This Firefox" → **Load Temporary Add-on** → `manifest.json` in the folder. Firefox only keeps signed add-ons, so this one goes away when Firefox closes.

## Tests (for developers)
`run_tests.bat` (or `python -m pytest`) runs every test. No internet is needed: the tests imitate servers without Range support, servers that drop connections or limit them, a fake proxy and a fake PyPI on a local server. The extension's logic is also tested with `node`. The English interface and the English installer are really opened in a process of their own, and the tests check that no Turkish text is left on screen. Tests that need a real FFmpeg are skipped without ffmpeg in `ffmpeg/` (or on PATH), window tests without a display, extension tests without node. The setup package tests (`-m installer`) run the real `DISO-Setup` file in a temporary place if the package was built; they never touch your real Start menu or registry.
- Only the quick tests: `python -m pytest -m "not gui and not ffmpeg and not exe and not installer"`
- One file: `python -m pytest tests/test_downloader.py`
- Check the installation without opening a window: `python main.py --selftest result.json`

## Troubleshooting
- **Updates:** at every start DISO checks yt-dlp, yt-dlp-ejs and FFmpeg and downloads newer versions itself (checked with SHA-256). If a new yt-dlp does not work, it goes back to the previous one by itself. See the state and check by hand in the `⟳ Updates` window.
- **If YouTube/Instagram suddenly stop working:** `⟳ Updates` → "Check" → restart DISO. yt-dlp is updated inside the program; nothing needs to be rebuilt.
- **If YouTube says "no formats found":** the Deno that comes with the setup package is enough. If you run from source, install it once with `winget install DenoLand.Deno`.
- **Videos that need a login:** pick the browser you are logged in with in the "Login cookies" menu (Firefox works best), or use the browser extension.
- **Google Drive / Mega / MediaFire pages** are not direct download links; DISO cannot press a button on a web page.

## ✉ Contact us
Found a bug or have an idea? [Open a new issue on GitHub](https://github.com/muslimekc2112/DISO/issues/new); English or Turkish are both fine. When reporting a bug, first press Settings → **ℹ About** → **📋 Copy details** in DISO and paste the text into the issue; the **✉ Contact us** button opens the same page. The log file helps too: `%LOCALAPPDATA%\DISO\diso.log`.

How it works, in detail: `HOW_IT_WAS_MADE.txt` (in Turkish: `NASIL_YAPILDI.txt`). Version history: [`CHANGELOG.md`](CHANGELOG.md). License: MIT (`LICENSE`).
