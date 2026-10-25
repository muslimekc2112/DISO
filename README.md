<div align="center">

<img src="assets/icon.png" alt="DISO" width="112">

# DISO

**A download manager for files, videos and music, with a full music player built in.**

[![Latest version](https://img.shields.io/github/v/release/muslimekc2112/DISO?label=version&color=2ea44f)](https://github.com/muslimekc2112/DISO/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/muslimekc2112/DISO/total?label=downloads&color=blue)](https://github.com/muslimekc2112/DISO/releases)
![Windows 10 | 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![English | Türkçe](https://img.shields.io/badge/language-English%20%7C%20T%C3%BCrk%C3%A7e-e30a17)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

**English | [Türkçe](README.tr.md)**

### [⬇ Download the latest version](https://github.com/muslimekc2112/DISO/releases/latest)

</div>

---

Paste a link and leave the rest to DISO: **files** split into parts over many connections (like IDM / FDM), **videos as MP4**, **music as MP3**, from YouTube, Instagram, TikTok, X and many more sites, plus **torrents**. Switch to the **music player** with one click: playlists, lyrics, an equalizer, a visualizer and songs found and downloaded straight from YouTube Music. A **browser extension** sends links, whole series and videos playing on any site to DISO.

## Contents
- [What it does](#-what-it-does)
- [Installing](#-installing)
- [Downloading](#-downloading)
- [Music player](#-music-player)
- [Browser extension](#-browser-extension)
- [Settings](#-settings)
- [Language](#-language)
- [What's new](#-whats-new)
- [Troubleshooting and questions](#-troubleshooting-and-questions)
- [For developers](#-for-developers)
- [Contact](#-contact)

## ✨ What it does

| | |
|---|---|
| ⚡ **Fast downloads** | Files are split into parts and downloaded over many connections at once. Unfinished downloads go on from where they stopped, even after a restart; a dropped connection is retried by itself. |
| 🎬 **Video and MP3** | YouTube, Instagram, TikTok, X and the many other sites yt-dlp knows. Choose the quality, download only a part of a video, get subtitles, MP3 with cover art. |
| 🎞 **Videos from any site** | The browser extension catches the videos (HLS / DASH streams too) a page plays, even when DISO cannot read the site itself. **Series mode** downloads a whole series episode by episode. |
| 🧲 **Torrents** | Magnet links and `.torrent` files, with a choice of which files to download. |
| 🎵 **Music player** | Playlists, gapless playback, a wave progress bar, lyrics that scroll with the song, an 8-band equalizer, playing speed and pitch, a visualizer, a mini player. |
| 🔍 **Find songs** | Search YouTube Music inside DISO, preview 30 seconds and download as MP3 straight into a playlist. |
| 🛡 **Safe** | Every finished download is scanned by Windows Defender. Updates are checked with SHA-256. Nothing is downloaded without you asking. |
| 🕹 **Your look** | **Standard** (recommended: modern, with colourful pictures on the buttons), New, Classic or **Nostalgia** (the grey download managers of the 2000s); an accent colour of your own, dark or light, English or Turkish. |

## 📥 Installing

**Requirements:** Windows 10 or 11. Nothing else: Python, FFmpeg, yt-dlp and the Deno that YouTube needs are all inside the package.

1. Download **`DISO-Setup-<version>.exe`** from the [latest release](https://github.com/muslimekc2112/DISO/releases/latest).
2. Double-click it and press **Install**. Windows asks for administrator rights: say **Yes**. DISO is installed for everyone on the PC in `C:\Program Files\ISO\DISO`.
3. Setup asks **which browsers should get the extension** and helps you add it (see [Browser extension](#-browser-extension)).

Setup adds Start menu and desktop shortcuts, appears in the Windows "Apps" list and, if you like, starts DISO together with Windows.

> **"Windows protected your PC" / "unknown publisher"?** The package is not digitally signed, so Windows warns about it. Press **More info → Run anyway**.

- **🔄 Updating:** DISO tells you when a new version is out. `⟳ Updates` → **DISO** → **Update** downloads the setup, checks it with SHA-256 and installs it (Windows asks for permission), then DISO opens again with the new version. Nothing is downloaded unless you ask. Running a new setup file by hand works too: it closes a running DISO and installs into the same folder. Your settings and playlists stay.
- **Coming from the old version (Hızlı İndirici):** setup removes the old one itself and moves your settings, playlists and download list to `%LOCALAPPDATA%\DISO`. Nothing is lost.
- **Uninstalling:** Settings → Apps → DISO → Uninstall, or right-click DISO in the Start menu → Uninstall, or "Uninstall DISO" in the Start menu. Only what setup put there is deleted. It asks whether your settings, playlists and the songs you found in the music player should go too. What you downloaded to your download folder is **never** touched.
- **Silent install:** `DISO-Setup-<version>.exe --silent [--dir "C:\path"] [--no-desktop] [--autostart]`, and to remove it `DISO.exe --uninstall --silent [--remove-data]` (the DISO.exe in the install folder). Log: `%TEMP%\DISO-kurulum.log`.

## 🚀 Downloading

### The basics
- Paste a link and press **⬇ Download**. In **Automatic** mode DISO works out by itself whether it is a file or a video.
- `📄` adds every link in a `.txt` file; `Ctrl+V` puts the links on the clipboard into the list. A link already in the list is not added again.
- With **📋 Watch clipboard** on, copying a link brings a small window to the corner: **⬇ Download**, **🎬 MP4**, **🎵 MP3** or **No** (also while DISO is in the tray).
- Every row has ⏸ / ▶ (pause / resume), 📂 (open folder) and ✖ (remove), a **right-click** menu, and double-click to open. The coloured strip on the left shows the state: downloading, done, error, paused.
- The list has search, filters, sorting and checkboxes for working on several rows at once. `Ctrl+F` search, `Ctrl+A` select all, `Delete` delete the selected ones.
- **⏫ Move to the front:** right-click a waiting download and it is the next one.
- **📈 Speed graph:** the last minute of speed under the list (green on black in Nostalgia, and in each download's progress window).
- **Folders by type** sorts files into Video, Music, Archives, Documents, Programs, Images and Other.
- A sound and a Windows notification (with DISO's name and icon) tell you when a download is done.

### Videos and music
- The **ℹ** button shows a link's qualities, sizes and subtitle languages; download the quality you want, or MP3, with one click.
- **✂ Download only a part:** type a **Start** and an **End** in the ℹ window (`1:30`, `1:02:03` or seconds). Only that part is downloaded, saved like `Name [1.30–2.45].mp4`.
- **Playlists:** with **Playlist** ticked, adding a playlist link lets you choose which videos to download.
- **Subtitles** (Turkish / English / all languages) are saved as `.srt` next to the video and put inside the MP4 as a subtitle track. If YouTube refuses its own translation, the subtitles in the video's language are saved and the row says so. The video is always downloaded, even when the subtitles are not.
- MP3s get the video's thumbnail as **cover art**.
- **📺 Followed channels** (📺 in the link row): paste a channel's link, its `@name` or one of its videos and press **Follow**. DISO looks at the channels now and then (every 30 minutes … once a day) and sends a **notification** when a new video comes. **It never downloads anything by itself:** pick what you want as **MP4** or **MP3**, clear the rest with **Seen**.
- **Stopped streams go on:** a paused HLS / DASH download, or one left half done when DISO closed, keeps the pieces it has and continues from there.

### Torrents
- Add a **magnet link**, a `.torrent` link or a `.torrent` file with `📄`. aria2 does the work; it is downloaded once with the first torrent (~2.5 MB, checked with SHA-256).
- **🧲 Choose the files:** before a torrent with several files starts, pick what you want from its folder tree (All / Videos / Music …), with the chosen size and the free room on the disk. Right-click → **Choose the files…** changes it while it downloads.
- A finished torrent is not shared on; DISO is a downloader.

### Safety and repair
- **🛡 Windows Defender on every download:** every finished download (torrent folders too) is scanned and the result is written under it: "🛡 Windows Defender: clean" or "⚠ found a threat and quarantined it". When Defender is off because another antivirus is used, DISO says so.
- **🔧 Check / repair the file** (right-click a finished download): when only the end is missing, only the missing part is downloaded; a broken file can be downloaded again.
- **🩺 Health check** (Settings → Backup and help): the internet, YouTube, GitHub, yt-dlp, FFmpeg, Deno, aria2, the extension, the download folder and the proxy are tried one by one, with a fix button next to what can be fixed.
- **🐞 Report a problem:** makes a zip with the details and opens a new issue page on GitHub. Playlists, history, cookies and passwords are never in it.

### ⏰ Scheduler (downloading at night)
Turn on Settings → **Scheduler** and type a start time (and, if you like, an end time), for example `02:00`–`07:00`. New downloads wait until the start time; at the end time the running ones pause and go on at the next start.

## 🎵 Music player

The **Download mode | Music player mode** switch at the bottom of the window opens the music player; the switch fades softly from one window to the other. Downloads go on in the background and the music keeps playing when you switch.

### Playing
- Double-click a song to start from it. Play / pause, previous / next, volume, **🔀 Shuffle** and **🔁 Repeat** (off / list / one song). `Space` plays / pauses.
- **〰 The progress bar is the song's wave:** loud parts are tall bars, quiet ones short. Click or drag to jump; hovering shows the time.
- **⏭ No gap between songs:** the next song waits ready on a second player and starts the very moment the current one ends.
- **⏪5 / 5⏩** and **← / →** go 5 seconds back / forward (held down they keep going). **↑ / ↓** turn the volume up / down, faster while held.
- **⏩ Playing speed** (the `1x` button): 0.25x to 4x, and the **pitch** ±6 semitones; the sound stays clean.
- **🎛 Equalizer:** 8 bands (60 Hz – 15 kHz) and ready-made settings (Bass boost, Treble boost, Vocal, Pop, Rock, Electronic, Hip-hop, Classical, Acoustic, Night). Left flat, the sound does not change at all.
- **🎚 Crossfade:** while a song fades out the next one fades in over 3, 6 or 10 seconds.
- **🔊 Even out the volume:** every song's loudness is measured once (EBU R128), so the volume does not jump between songs.
- **😴 Sleep timer:** after 15–90 minutes, or when the current song ends, the music **fades out softly** and stops; your volume is as it was afterwards.
- **Go on where you left off:** after a restart the last song shows as "Where you left off" and ▶ goes on from the same second.
- **⏭ Play next / ➕ Add to queue** (right-click): plays the songs you pick after the current one without changing the list; **📋 Queue** shows them.
- **The media keys** on your keyboard work whether DISO is in front or not, and only while music is playing or paused. The Windows media panel and the taskbar preview show the song, artist and cover with ⏮ ⏯ ⏭.
- **🗗 Mini player:** a small always-on-top player in the corner; ⤢ goes back to the big window.

### Looks
- **🎨 The colour of the music:** the player's block glows in the cover's colours with every moment of the song, like YouTube's ambient light (can be turned off in the ⚙ menu).
- **🎤 Karaoke** (⚙ menu): the singer's voice goes down (the bass stays) and the lyrics flow on the visualizer. Best with headphones or two speakers.
- **🔗 Send a list to a friend** (⚙ menu): you get a code like `K7P2-QM4X` and a link; your friend opens it with **📥 Open a shared list** and the songs download as MP3.
- **🌌 Visualizer:** bars, wave or ring. In the ring the cover beats in the middle; the colours can come from the cover. ⏮ ⏪5 ⏯ 5⏩ ⏭ at the bottom, **F11** for full screen.
- The playing song's **cover art** and album show in the player, and the cover melts into the next one when the song changes.

### Playlists
- Make **as many playlists as you like** (`＋` new, `✎` rename, `🗑` delete). They are kept in `%LOCALAPPDATA%\DISO\playlists.json`.
- Add music with `＋ File` and `📁 Folder`, order the songs with `▲` `▼` (or `Ctrl+↑/↓`), take them out with `Delete`. The files themselves are never deleted.
- The table shows **artist, title and length** from the file's tags, and the total length of the list.
- **⇅ Order a list:** my own order, newest first / last, A → Z, Z → A (in Turkish alphabetical order), most played first. Your own order is always kept.
- **🔀 Shuffle** gives the list a new random order for good (`Ctrl+Z` brings the old one back).
- **Search the list** with `Ctrl+F`; click a column title to sort by it.
- **✨ Smart lists:** **⭐ Most played**, **🆕 Recently added** and **💤 Never played** fill themselves from all your lists.
- Finished music downloads **go into a playlist by themselves**: a YouTube playlist into a list with its own name, a single MP3 into "Downloaded" (Settings → "Put finished music into a playlist" turns this off).
- A song whose file was deleted leaves the list by itself. A song on a USB stick that is not plugged in is not counted as deleted.
- **📤 / 📥 .m3u lists:** export a list as `.m3u8` for a phone or another player, or import a `.m3u` / `.m3u8` / `.pls`.

### Lyrics and song details
- **🎤 Lyrics:** when a song has lyrics, a **🎤 Lyrics** button appears in the player. Timed lyrics scroll with the song: the line being sung is big and coloured, clicking a line jumps there, A− / A+ change the size. Lyrics come only from **YouTube Music** (for a song downloaded by DISO, that very video's lyrics; otherwise the YouTube Music song with the same title and artist, the one closest in length), so they are never another song's that only shares its name. They are saved next to the song as `song.lrc`.
- Wrong lyrics? Right-click → "🔄 Wrong lyrics, look again". **✎ Write or paste lyrics** by hand too.
- **🏷 Edit a song's details** (right-click): name, artist, album, year, genre and the cover picture are written into the file itself; the sound is not re-encoded.
- **🖼 Find the cover online** for one song or for every song in a list that has none.
- **✏ Rename files from a pattern** like `{artist} - {title}`, with a preview and **↶ Undo**.

### 🔍 Find songs
Type a song name (or a YouTube link) in the **🔍 Find songs** tab, optionally an artist next to it, and press Enter. The search is done only on **YouTube Music** and brings only songs: no videos, lyric videos or shorts. Songs matching what you typed come first, the most listened to first.
- **Double-click** a song, or select it and press **⬇ Download (MP3)**. It downloads in the background with its cover while you keep listening.
- When it is done DISO asks **which list it should go into**. The list you chose last is offered first next time.
- **🎧 Preview:** listen to 30 seconds first, starting where the song is replayed most (the chorus, usually).
- While you type, **YouTube suggestions** and **your recent searches** appear.
- Paste a **YouTube Music / YouTube playlist link** and **⬇ Download all** downloads every song as MP3 into a playlist with the list's name, in order.
- The same song is never downloaded twice. Songs are kept in `%LOCALAPPDATA%\DISO\Müzik` (the **📂 Downloaded** button opens it).

**Formats:** mp3, wav, wma, m4a, aac, flac, ogg, opus, aiff, wv, ape, mka.

## 🧩 Browser extension

For **Chrome, Edge, Brave, Opera, Vivaldi** and Firefox, like IDM's.

- **Right-click a link → "Download with DISO":** the download starts in DISO at once. It also works on a video, sound or picture, on selected text (every link in it), and with **"Download all file links on this page with DISO"**.
- **🎞 Videos from any site:** the extension finds the videos a page plays (HLS `.m3u8`, DASH `.mpd`, video and sound files, also inside hidden players and streams hidden behind names like `.txt` or `.png`) and shows how many on its button. Choose them, the quality and the subtitles, and download as **MP4** or **MP3**. The player's headers go along, so sites that only answer their own player download too. Copy-protected (DRM) streams cannot be downloaded.
- **📺 Series mode:** on a series page the extension finds the episodes (Episode 1, S02E03 …). The chosen ones are opened one by one in a small muted window, their videos caught and sent to DISO as "Series - S01 Episode 02", into the series' own folder.
- **DISO opens by itself when it is closed:** the extension starts it (through the browser's "native messaging", the way IDM does), waits until it is ready and hands the link over.
- **Catching the browser's own downloads** (optional): files of the chosen types or above a size go to DISO instead. If DISO cannot start, the browser simply goes on.
- The toolbar button shows **what DISO is downloading right now** (count and speed) and has **▶ Open DISO**, "download this tab" and "download this tab as MP3".
- For sites that need a login, the browser's session is passed along; cookies are never written to disk. DISO listens only on this PC and accepts requests only from the extension, never from web pages.

**Adding it:** DISO asks once after it starts ("Shall we add DISO to your browser?"), setup asks too, and the same guide is always in Settings → **🧩 Add to browser**. Browsers only install extensions from their stores by themselves, so it takes three clicks: the guide opens the extensions page and the extension's folder and copies the folder's path; turn on **Developer mode**, press **Load unpacked**, paste the path (`Ctrl+V`) and press **Select Folder**. The folder is `C:\Program Files\ISO\DISO\browser_extension`, and DISO's updates update it there too. The extension is also on the release page as `DISO-browser-extension-<version>.zip`.

**Firefox:** use the guide (it prepares a Firefox copy of the extension), then `about:debugging` → "This Firefox" → **Load Temporary Add-on** → its `manifest.json`. Firefox only keeps signed add-ons, so it goes away when Firefox closes.

## ⚙ Settings

- **Downloads:** how many at the same time (1–8), a total **speed limit**, automatic retries, a **proxy** (http / socks5, with a **Test** button), the scheduler, and what to do **when all downloads finish** (close DISO / sleep / shut down the PC).
- **System:** keep running when closed (system tray), start with Windows, notifications, the log file.
- **Look:** theme (dark / light / system), **accent colour** (pink, blue, green, orange, purple, red) and style: **Standard (Recommended)** (the first look of a new computer: New's colours with Nostalgia's colourful pictures), **New**, **Classic** or **🕹 Nostalgia** (a menu bar, a toolbar of big pictures, categories on the left and a table, like the download managers of the 2000s, in light or dark grey). DISO opens again at the same place after a change.
- **👤 Account:** create one (name, user name, Gmail confirmed by a 6 digit code) or sign in, optional; your name is at the top right. The settings, playlists, channels and history are synced between your computers; on a new computer the lists' songs can be downloaded with one click. **💻 Signed-in computers** lists them all and signs any of them out; **🗑 Delete account** removes it for good.
- **👥 Friends, chats and groups:** add friends by user name (e-mails are never shown), chat with them and in groups (admins, mentions), recommend songs, send songs, playlists, pictures and files with ➕, reply, react, see what they like (👍 / 👎) and listen to now; everything comes as a notification, within a second.
- **👋 Tours:** a step-by-step tour of the download window (first start) and of the music player (the first time it opens), some steps tried by hand; open them again in Settings → Backup and help.
- **💾 Backup and help:** back up settings, playlists, the download list, history and channels in one `.disoyedek` file and restore it on another PC; **📊 Download history**; **⌨ Keyboard shortcuts** (**F1** everywhere); the health check and problem reports.
- **ℹ About** (or click the version badge in the title): the version and where DISO and its data are. **📋 Copy details** copies the versions of DISO, Windows, yt-dlp, FFmpeg and Deno.

Everything you choose is remembered.

## 🌐 Language
DISO, its setup and its browser extension speak **English and Turkish**. On the first start DISO is in Turkish if Windows is, and in English otherwise. Switch at any time with **TR | EN** at the top left, or Settings → **Language** (DISO restarts). The setup and uninstall windows have a **Türkçe | English** switch too; the browser extension follows the browser's language.

## 🆕 What's new
The newest version is always on the [releases page](https://github.com/muslimekc2112/DISO/releases/latest); every change is in [`CHANGELOG.md`](CHANGELOG.md). The highlights of 1.7:
- **🏗 Supabase** is the new foundation of the account (old Firebase accounts are made again), with **🔐 6 digit codes** instead of links.
- **👥 Groups** with admins, **➕ attachments** (songs, playlists, pictures, files), replies, reactions, read marks and messages **within a second**.

And of 1.6:
- **👥 Friends:** add friends by user name, **💬 chat**, **🎵 recommend songs**, **👍 / 👎** and see what friends like and listen to now; **🔔 notifications** for all of it.
- **🗑 Delete account** for good.

And of 1.5:
- **🎨 Standard (Recommended):** a new first look, modern with colourful pictures on the buttons, and an **accent colour** of your own.
- **👤 DISO account, finished:** create an account (name, unique user name, Gmail confirmed by a link) or sign in; your name at the top right; **💻 signed-in computers**; on a new computer the data and the lists' songs come along.
- **🔗 Send a playlist to a friend** with a code, and **🎤 karaoke**.
- **👋 Tours** of the download window and the music player, with steps you try yourself.
- **⚡ Settings** open at once and resize smoothly.

1.4 brought the DISO account (settings, playlists, channels and history synced). Before that, in the 1.3 line: a **〰 wave progress bar**, **⏭ no gap between songs**, a **😴 sleep timer that fades out**, **📺 series mode** in the browser extension, **🎨 the colour of the music**, **✨ soft transitions** and a **⚡ faster** start.

## 🛠 Troubleshooting and questions
- **Windows says "unknown publisher".** The package is not digitally signed. Press **More info → Run anyway**.
- **YouTube / Instagram suddenly stopped working.** `⟳ Updates` → **Check**, then restart DISO. At every start DISO checks yt-dlp, yt-dlp-ejs, FFmpeg and Deno and downloads newer versions itself (checked with SHA-256); if a new yt-dlp does not work, it goes back to the previous one by itself.
- **YouTube says "no formats found".** The Deno in the setup package is enough. When running from source, install it once with `winget install DenoLand.Deno`.
- **A video needs a login.** Pick the browser you are logged in with in the **Login cookies** menu (Firefox works best), or use the browser extension.
- **Google Drive / Mega / MediaFire pages** are not direct download links; DISO cannot press a button on a web page.
- **Do I need to install FFmpeg?** No. The setup package has it; when running from source DISO downloads it the first time it is needed (~115 MB, checked with SHA-256).
- **Where are my settings and lists?** In `%LOCALAPPDATA%\DISO`. They are written safely to disk and a last good copy (`.bak`) is kept, so a power cut does not empty your lists.
- **Something else?** Settings → **🩺 Health check** finds most problems and fixes many with one click.

## 🔨 For developers

<details>
<summary><b>Running from source, building, tests</b></summary>

### Running and building
1. Install Python 3.10+ (tick **"Add Python to PATH"**).
2. Double-click `run.bat`: it installs the libraries and starts DISO. By hand: `pip install -r requirements.txt`, then `python main.py`.
3. `build.bat` makes a portable single-file `DISO.exe` that needs no install (`build.bat --no-ffmpeg` for a smaller one). It unpacks itself at every start, so it opens a few seconds slower.
4. `python tools/build_installer.py` makes the setup package: it builds DISO as a folder (`build\app\DISO`), downloads Deno and checks its SHA-256, and writes `dist\DISO-Setup-<version>.exe`. The installed DISO opens in 2–3 seconds.
5. The icons are made from one picture: after changing `IKON\icon.png`, run `python tools/make_icons.py`.

The name, publisher, version and GitHub address are in one place: `app/brand.py`. The interface texts are written in Turkish; their English is in `app/lang_en.py` (the keys are the Turkish texts as shown on screen).

### Tests
`run_tests.bat` (or `python -m pytest`) runs every test, with no internet needed: the tests imitate servers without Range support, servers that drop or limit connections, a proxy and PyPI on a local server. The extension's logic is tested with `node`. The English interface and setup are really opened, and the tests check that no Turkish text is left on screen. Tests that need FFmpeg, a display, node or aria2 are skipped when those are missing. The setup tests (`-m installer`) run the real `DISO-Setup` in a temporary place and never touch your Start menu or registry.
- Only the quick tests: `python -m pytest -m "not gui and not ffmpeg and not exe and not installer"`
- One file: `python -m pytest tests/test_downloader.py`
- Without windows popping up on your screen: `python tools/run_hidden.py -- python -m pytest tests` (the tests run on a desktop of their own; the few that need the taskbar are skipped there)
- Check the installation without a window: `python main.py --selftest result.json`

How DISO works inside, in detail: `HOW_IT_WAS_MADE.txt` (in Turkish: `NASIL_YAPILDI.txt`).

</details>

## ✉ Contact
Found a bug or have an idea? [Open a new issue on GitHub](https://github.com/muslimekc2112/DISO/issues/new), in English or Turkish. When reporting a bug, press Settings → **ℹ About** → **📋 Copy details** in DISO first and paste the text into the issue (the **✉ Contact us** button opens the same page). The log helps too: `%LOCALAPPDATA%\DISO\diso.log`.

## 📄 License
MIT: see [`LICENSE`](LICENSE). Version history: [`CHANGELOG.md`](CHANGELOG.md).
