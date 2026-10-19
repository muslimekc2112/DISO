# Version history

**English | [Türkçe](CHANGELOG.tr.md)**

## 0.11.2 beta
- **Fixed:** Chrome showed the warning "'background.scripts' requires manifest version of 2 or lower" on the extensions page (harmless, but it looked like an error). Chrome and Firefox now have separate manifests: `manifest.json` holds only what Chrome understands, `manifest.firefox.json` is Firefox's. The guide's Firefox button prepares a Firefox copy by itself; the release also has a separate Firefox zip.
- **Fixed:** with the portable `DISO.exe` the extension's folder (`%LOCALAPPDATA%\DISO\browser_extension`) was only brought up to date when the guide was opened; now at every start, so a newer DISO.exe also updates the extension (press the extension's reload button in the browser, or restart the browser).

## 0.11.1 beta
- **DISO offers the browser extension itself:** a few seconds after it starts, if the extension is not in a browser yet, DISO asks "Shall we add DISO to your browser?" — **Add the extension** opens the step-by-step guide, **Remind me later** asks again in three days, **Don't ask again** never asks. Once the extension has talked to DISO, the question goes away for good. Not asked when DISO starts in the tray, when links from the browser are switched off, or on a PC without a supported browser.
- Clearer wording about the extension in setup, the guide and the extension's settings.

## 0.11.0 beta
**New: the browser extension works like IDM's**
- **DISO opens by itself:** "Download with DISO" in the browser starts DISO when it is closed (through the browser's native messaging, as IDM does), waits until it is ready and the download starts at once. Setup registers it for every browser; DISO itself also registers for the current user at every start, so a portable `DISO.exe` works too. Uninstalling removes it.
- **Setup asks which browsers** should get the extension (Chrome, Edge, Brave, Opera, Vivaldi, Firefox — the ones on the PC are found and ticked) and then opens a guide: it opens the browser's extensions page and the extension's folder and copies the folder's path. The same guide is in DISO: Settings → **🧩 Add to browser**.
- The extension is installed next to DISO (`C:\Program Files\ISO\DISO\browser_extension`) and gets a fixed id, so it stays the same extension through updates.
- **"Download all file links on this page with DISO"** in the right-click menu of a page.
- The toolbar button shows **what DISO is downloading** (count, speed, queue) and has **▶ Open DISO**; its buttons work while DISO is closed too.
- Caught browser downloads wait while DISO starts and move over to it; if DISO cannot start they go on in the browser.
- A new setting in the extension: "Open DISO when it is closed" (on by default).

## 0.10.1 beta
**New**
- **Two languages everywhere:** the app, the setup and uninstall windows, the browser extension and every document on GitHub (README, version history, the technical description, the extension and FFmpeg notes) are in English and Turkish.
- On the first start the language comes from Windows: Turkish if Windows is in Turkish, English otherwise. Change it any time in Settings → Language. Setup uses the language chosen in DISO; the extension uses the browser's language.
- **✉ Contact us:** a button in the About window that opens a new issue page on GitHub. Problems are now reported on GitHub instead of "send it to me".

- The setup file is now called `DISO-Setup-<version>.exe` (it was `DISO-Kurulum-…`), the same in both languages.

**Fixed**
- Texts that were still Turkish in the English interface: the filter and sort choices ("Finished", "Name (A→Z)"), the "Audio (MP3)" download type, the state of a paused row, "Audio only (MP3)" and the subtitles line in a link's details, the "Install" button and "Last check" in the updates window, "Today/Yesterday", "in total" and "Most from" in the history window, the music player's "Getting ready to play…" and "Could not play it, went on to the next one" notes, and the error texts of the song search.

## 0.10.0 beta
The program was renamed **DISO** (publisher: ISO) and became its first beta. The number went down from 1.1.0 to 0.10.0: too early to say "ready", "beta" is honest.

**New**
- New name, new icon, a purple palette that matches it; a BETA badge in the title.
- **About window** (in Settings, or click the BETA badge): version, folders, and "copy details" to the clipboard with one click.
- The version is remembered: a welcome on the first start, "updated to …" after an update.
- **Setup package** (`DISO-Kurulum-<version>.exe`): needs no Python, installs for everyone into `C:\Program Files\ISO\DISO`, brings Deno along and has an uninstaller. It removes the old "Hızlı İndirici" install and moves its data.
- Music player: a table (number, song, artist, length), cover art, total length; finished music downloads go into a playlist by themselves; a download's right-click menu adds it to a list.
- **🔍 Find songs:** search YouTube from the music player, download as MP3 in the background (only the percentage shows), and when done put it in a list via a "which list?" question. Songs go to `%LOCALAPPDATA%\DISO\Müzik`.
- Music player: deleted files leave the list by themselves, search in the list, sort by clicking a column, a right-click menu (show in folder, add to another list), go on where you left off, a sleep timer, the keyboard's media keys.
- **🎤 Lyrics** (LRCLIB): come by themselves with found songs, a lyrics window that scrolls with the song, click a line to jump there; a 🎤 button in the player for songs that have lyrics.
- **🔀 Shuffle the list** (undo with Ctrl+Z).
- YouTube titles like "Artist - Song" are split into artist and song (the channel name is not taken for the artist).
- Friendlier interface texts; the installer speaks in the same casual tone.
- **Music player:** play next / add to queue, crossfade between songs, a mini player, ⏮ ⏯ ⏭ in the taskbar preview, the song and cover in the Windows media panel.
- **Find songs:** a 30 second preview, YouTube suggestions and search history, "Download all" from a YouTube Music playlist/album link (with the list's name, in order).
- **📊 Download history and statistics**, **💾 back up / restore**, **⌨ keyboard shortcuts (F1)**, **English interface** (Settings → Language).

**Changed**
- Data lives in `%LOCALAPPDATA%\DISO` (it used to be `.hizli_indirici` in the user folder). It is moved by itself on the first start.
- Setup is for all users and asks for administrator rights (it used to be per user, without rights).
- The browser extension is 0.10.0 too; its Firefox id is `diso@iso.local`.

**Fixed**
- **The music player could not play some songs**: MP3s with large cover art (over ~128 KB, Windows cannot open them) and videos with Opus sound (VP9/AV1 MP4). Now a playable copy is made in the background (`%LOCALAPPDATA%\DISO\play_cache`, at most 1 GB; the file itself is not touched); meanwhile "⏳ Getting ready to play…" shows, then the song you clicked plays. It used to skip silently to the next one.
- New MP3 downloads embed a cover of at most 600 px / 90 KB, so the problem does not come up in the first place.
- Flickering texts (things that did not change are no longer redrawn).
- The settings window disappearing when the theme changed.
- An error when going from a song with cover art to one without, and the music window's clock stopping.
- **Downloads with subtitles:** when YouTube refused the subtitles (common for translated ones, "429 Too Many Requests") the fallback path failed the whole video; on the fast path the subtitles silently did not come. Now subtitles never break a video: they are tried once more, the video's own language is saved if that fails too, and the subtitles are embedded in the MP4 as well.
- **Faster start:** setup now installs DISO as a folder (DISO.exe + `_internal`). The single big exe unpacked ~115 MB to a temporary folder at every start (6–7 s); now it is 2–3 s. The single-file exe stays as the portable version that needs no install. Setup records nested folders one by one: nothing empty is left behind after uninstalling or after an undone install, and installing over the old single-file install works.
- **Faster closing:** windows disappear the moment you press Close; closing waited 3 s while the music list was reading tags (now ~0.3 s); a download whose details are being fetched does not hold up closing, and saving waits at most 6 s (it used to be 15).
- **Downloads start sooner:** no video download started until the update check of yt-dlp/FFmpeg at start-up was over (up to 90 s); now they don't wait, and yt-dlp is prepared in the background at start. For well-known sites like YouTube, Instagram and TikTok the "file or video?" question is skipped; a stuck request is retried after 15 s instead of 30.
- The DISO logo instead of customtkinter's blue icon in the title bar of the music player, lyrics, Settings, About and every other window; the real logo in the music player's header too.
- **Wrong lyrics:** LRCLIB could bring the lyrics of another song with the same name (only the title was compared). Now lyrics come from YouTube Music first, from the downloaded video itself; LRCLIB's timings are only used when the text is the same, and LRCLIB on its own must match the artist too. "Look again" for old lyrics that stayed wrong.
- The uninstaller also deletes the empty `C:\Program Files\ISO` folder.
- In the installer/uninstaller: files missing after an error halfway through an upgrade, the uninstaller closing its own process, the window freezing.
