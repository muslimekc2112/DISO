# Version history

**English | [Türkçe](CHANGELOG.tr.md)**

## 1.1
- **🕹 Nostalgia look:** Settings → System → Style → **Nostalgia** (or View → Look in the menu). The grey Windows of the 2000s and a window like the download managers of that time: a menu bar (Tasks, Downloads, View, Tools, Help), a toolbar of big pictures (New download, Resume, Stop, Stop all, Delete, Delete completed, Options, Scheduler …), categories on the left (Video, Music, Compressed, Documents, Programs, Unfinished, Finished, Failed), the downloads as a table (File name, Size, Status, Time left, Speed …; click a heading to sort) and a status bar. Double-click a running download: its progress window with the green block bar opens; a finished one opens the file. The settings are tabs, the music player has a menu bar too; everything in Tahoma, grey and always light.
- **Everything stays where it was when the look changes:** after a new style or language DISO opens again at the same place and size, in the music player if you were there, with the settings open (on the same tab) if they were; a song that played goes on from where it was.
- **Windows only:** the Linux version is dropped (1.0's Linux packages stay as they are; no new ones will come).
- **🔄 DISO updates itself:** it tells you when a new version is out; `⟳ Updates` → DISO → **Update** downloads it, checks it with SHA-256, installs it and opens the new version. Nothing is downloaded unless you ask; say "no" to Windows' permission question and DISO just goes on.
- **📺 Followed channels:** a notification when a channel you follow gets a new video; nothing is downloaded by itself, you download what you pick as MP4 / MP3.
- **✂ Video clipping:** type a Start / End in the ℹ window and only that part of the video is downloaded.
- **🎛 Equalizer:** 8 bands and ready-made settings; left flat, the sound does not change at all.
- **✨ Smart lists:** ⭐ Most played, 🆕 Recently added, 💤 Never played.
- **Fixed:** at the smallest window size "Watch clipboard" was cut off; in English, notices like "Added: MP3" were not translated.
- **Fixed (important):** with "Catch browser downloads" on, when the browser started the extension sent **all of the browser's old downloads** to DISO, which downloaded them again (and they were removed from the browser's download history). A starting browser also reports the downloads of its history as "new"; the extension now only catches downloads that are starting right then and never touches finished, broken off or old ones. To update the extension: `chrome://extensions` → DISO → ↻ (reload).
- **Find songs is YouTube Music only:** the results are songs only; no YouTube videos, lyric videos, music videos or shorts (videos are no longer added when few songs are found, and plain YouTube is no longer searched when YouTube Music cannot be reached; it tries once more and then says "Could not reach YouTube Music").
- **Lyrics only from YouTube Music:** LRCLIB is no longer used (it could bring the lyrics of another song with the same name). When the downloaded video has no lyrics, those of YouTube Music's song with the same title and artist, the one closest in length, are taken; Turkish letter differences ("Şımarık" / "Simarik") no longer get in the way. For old lyrics that stayed wrong: right-click → "🔄 Wrong lyrics, look again".

## 1.0
- **DISO 1.0: out of beta.** Everything below is in it, on Windows and now on Linux too.
- **Linux:** DISO now runs on Linux too: a `.deb` for Debian, Ubuntu, Mint … and a `.tar.gz` for any distribution (with `install.sh` inside, no administrator password needed). FFmpeg, yt-dlp and Deno come inside; DISO updates them there too (FFmpeg: BtbN builds, checked with SHA-256).
- **Setup and removal in two languages:** `install.sh` and `uninstall.sh` ask Türkçe / English; removing asks whether your settings, playlists and history should go too (the files you downloaded are not touched). "Uninstall DISO" is in the applications menu.
- **The music player on Linux:** FFmpeg decodes the sound and SDL plays it; every kind of file (Opus, Vorbis, FLAC …) plays without converting, with cross-fade and previews.
- **The browser extension on Linux:** the extension can start DISO when it is closed (a small file goes into each browser's own folder). The extension guide finds the browsers there too; **Chromium** is on the list now.
- **Start when I log in** (autostart), notifications (notify-send) and "shut down / sleep when done" work on Linux too.
- What stays Windows-only: the media keys, the taskbar preview buttons and Windows' media panel.
- The portable `DISO.exe` is no longer attached to the releases (use the setup).

## 0.11.5 beta
- **TR | EN at the top left of the main window:** change the language with one click (DISO offers to restart; the same as Settings → Language).
- **Fixed:** fast wheel scrolling in Settings (and the other scrolling windows) left copies of rows on the screen, so texts looked broken. Wheel steps are now added up, scrolled at once and painted right away.
- **Fixed:** the end of some texts was cut off: hints in Settings ("…I go on when it's back", "…a new list with their own name", "…keep going once started"), the version below Settings ("SO 0.11.4 be"), "Automatic (file / video)" in the main window, and long texts in Updates, Shortcuts, About and the extension guide when those windows were made smaller. Long texts now wrap at the width of the window; the version is at the top right of Settings.

## 0.11.4 beta
- **Language switch in the setup and uninstall windows:** **Türkçe | English** at the top right. The window opens in DISO's language (Windows' own if DISO never ran) and you can change it; once installing or removing starts, the language stays. The language chosen in setup becomes DISO's language too (your other settings are not touched).
- **Uninstalling:** right-click DISO in the Start menu → Uninstall opens Windows' list of apps; Uninstall there opens DISO's uninstaller, which asks about "Also delete my settings and playlists". "Uninstall DISO" in the Start menu opens the uninstaller directly.
- **Fixed:** switching to English while a window was open broke the choice buttons made before the switch.

## 0.11.3 beta
- **Find songs now searches YouTube Music:** shorts and ordinary videos no longer fill the results, songs do (up to 50). The ones that match what you typed come first, the most listened to first; a new **Plays** column shows how much each song is listened to. When few songs are found, YouTube Music's music videos are added. If YouTube Music cannot be reached, YouTube is searched (without shorts).
- **Artist / channel box:** type an artist's or a channel's name next to the search box to get only their songs. It works together with a song name or on its own (that artist's most popular songs); left empty it changes nothing. Case and Turkish letters do not matter ("simarik" = "Şımarık").
- **Fixed:** with MP4 or MP3 chosen as the download type, a plain file (zip, rar, exe, pdf…) was "converted" to video / sound. DISO now looks at what the link is and downloads such a file as it is; video sites, pages and sound / video files follow the choice.
- **The browser extension says what a link is:** file links and caught browser downloads go to DISO as files (the MP3 / MP4 choice in the app does not change them), page links are left for DISO to look at. The extension's button has **🎬 Download as MP4** and **🎵 Download as MP3** ("Download this tab" is gone); the page's right-click menu has both too.
- **Fixed:** Updates showed FFmpeg as "Your own install" although it came with DISO. The FFmpeg that comes with DISO is now DISO's own: when a newer one is out, DISO updates it itself. "Installed separately" is shown only for another FFmpeg installed separately on the PC.

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
