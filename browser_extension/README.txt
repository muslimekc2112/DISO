DISO — BROWSER EXTENSION / TARAYICI EKLENTİSİ
=============================================

(Türkçesi aşağıda.)

ENGLISH
-------

What does it do? (like IDM's extension)
  * Right-click a link -> "Download with DISO": the download starts in DISO at once.
  * Right-click a video / sound / picture -> the same menu
  * Right-click the page -> "Download this page with DISO (video)"
  * Right-click the page -> "Download all file links on this page with DISO"
    (links to the file types listed in the extension's settings: zip, exe, mp4, mp3, pdf ...)
  * Select text and right-click -> every link in the selection
  * DISO OPENS BY ITSELF when it is closed: the extension starts it, waits until it is ready and
    hands the link over (through the browser's "native messaging", the way IDM does it).
  * If you like, it catches the browser's own downloads and hands them to DISO
    (switched on in its settings; if DISO cannot be started, the browser downloads as usual).
  * The toolbar button shows what DISO is downloading right now and has "Open DISO".
  * For sites that need a login, the browser's session (cookies, page address) is passed to DISO.
    Cookies are never written to disk; they are kept in memory only while the download runs.
  * It speaks English or Turkish, following the browser's language.

Installing — the easy way
  Setup asks which browsers should get the extension and then opens a guide. Later the same guide
  is in DISO: Settings -> "Add to browser". It opens the browser's extensions page and this folder
  and copies the folder's path; then do the three steps below.

Installing — Chrome / Edge / Brave / Opera / Vivaldi
  1. Open the extensions page: chrome://extensions  (Edge: edge://extensions, Brave: brave://extensions,
     Opera: opera://extensions, Vivaldi: vivaldi://extensions).
  2. Turn on "Developer mode" (top right).
  3. "Load unpacked" -> choose this folder (browser_extension). Or drag this folder onto the page.
  The installed DISO keeps this folder in C:\Program Files\ISO\DISO\browser_extension; a portable
  DISO.exe in %LOCALAPPDATA%\DISO\browser_extension.

Installing — Firefox
  Firefox needs its own manifest (manifest.firefox.json; manifest.json is Chrome's). Easiest: use the
  guide in DISO (Settings -> "Add to browser" -> Firefox): it makes a Firefox copy of this folder. Or
  take DISO-firefox-extension-<version>.zip from the GitHub release.
  1. Type  about:debugging#/runtime/this-firefox  in the address bar.
  2. "Load Temporary Add-on" -> choose manifest.json in the Firefox copy (or the Firefox zip itself).
     (Firefox removes temporary add-ons when it closes; a lasting install needs a signed add-on.)

Opening DISO from the browser
  * DISO registers itself with the browsers when it is installed, and at every start (so open DISO
    once if you use the portable DISO.exe). Nothing else is needed.
  * It can be switched off in the extension's settings: "Open DISO when it is closed".

Using it
  * The port must be the same as Settings -> "Extension port" in the app (default 17653).
    Check it with the "Test the connection" button on the extension's settings page.

Safety
  * The app listens only on this PC (127.0.0.1); it is not open to the internet.
  * A web page cannot start a download in the app: only requests from browser EXTENSIONS are accepted.
  * Only this extension (its fixed id) may start DISO through native messaging.
  * The "Take links from the browser extension" switch in the app turns this feature off completely.


TÜRKÇE
------

Ne yapar? (IDM'in eklentisi gibi)
  * Bağlantıya sağ tık -> "DISO ile indir": indirme hemen DISO'da başlar.
  * Videonun / sesin / resmin üstüne sağ tık -> aynı menü
  * Sayfaya sağ tık -> "Bu sayfayı DISO ile indir (video)"
  * Sayfaya sağ tık -> "Bu sayfadaki tüm dosya linklerini DISO ile indir"
    (eklentinin ayarlarındaki dosya türlerine giden linkler: zip, exe, mp4, mp3, pdf ...)
  * Metin seçip sağ tık -> seçilen bağlantıların hepsi
  * DISO KAPALIYSA KENDİSİ AÇILIR: eklenti onu başlatır, hazır olmasını bekler ve linki verir
    (tarayıcının "native messaging" kanalıyla, IDM'in yaptığı gibi).
  * İstersen tarayıcının kendi indirmelerini yakalar ve DISO'ya yönlendirir
    (ayarlarından açılır; DISO açılamazsa tarayıcı normal indirir).
  * Araç çubuğundaki düğme DISO'nun şu an ne indirdiğini gösterir, "DISO'yu aç" düğmesi vardır.
  * Giriş gerektiren siteler için tarayıcının oturumu (çerez, sayfa adresi) DISO'ya iletilir.
    Çerezler diske yazılmaz, yalnızca indirme sürerken bellekte tutulur.
  * Tarayıcının diline göre Türkçe ya da İngilizce konuşur.

Kurulum — kolay yol
  Kurulum hangi tarayıcılara eklenti kurulacağını sorar ve sonra bir rehber açar. Aynı rehber sonra
  DISO'da da var: Ayarlar -> "Tarayıcıya ekle". Tarayıcının eklentiler sayfasını ve bu klasörü açar,
  klasörün yolunu panoya kopyalar; sonra aşağıdaki üç adımı yap.

Kurulum — Chrome / Edge / Brave / Opera / Vivaldi
  1. Eklentiler sayfasını aç: chrome://extensions  (Edge: edge://extensions, Brave: brave://extensions,
     Opera: opera://extensions, Vivaldi: vivaldi://extensions).
  2. Sağ üstten "Geliştirici modu"nu aç.
  3. "Paketlenmemiş öğe yükle" -> bu klasörü (browser_extension) seç. Ya da bu klasörü sayfaya sürükle.
  Kurulu DISO bu klasörü C:\Program Files\ISO\DISO\browser_extension içinde tutar; taşınabilir
  DISO.exe ise %LOCALAPPDATA%\DISO\browser_extension içinde.

Kurulum — Firefox
  Firefox kendi manifest dosyasını ister (manifest.firefox.json; manifest.json Chrome'unki). En kolayı:
  DISO'daki rehberi kullan (Ayarlar -> "Tarayıcıya ekle" -> Firefox): bu klasörün Firefox kopyasını
  hazırlar. Ya da GitHub sürümündeki DISO-firefox-extension-<sürüm>.zip dosyasını al.
  1. Adres çubuğuna  about:debugging#/runtime/this-firefox  yaz.
  2. "Geçici eklenti yükle" -> Firefox kopyasındaki manifest.json'u (ya da Firefox zip'inin kendisini) seç.
     (Firefox geçici eklentileri kapanınca siler; kalıcı kurulum için eklenti imzalanmalıdır.)

DISO'yu tarayıcıdan açmak
  * DISO kurulurken ve her açılışta kendini tarayıcılara kaydeder (taşınabilir DISO.exe kullanıyorsan
    DISO'yu bir kez aç). Başka bir şey gerekmez.
  * Eklentinin ayarlarından kapatılabilir: "DISO kapalıysa aç".

Kullanım
  * Bağlantı noktası uygulamadaki Ayarlar -> "Eklenti bağlantı noktası" ile aynı olmalı (varsayılan 17653).
    Eklentinin ayar sayfasındaki "Bağlantıyı dene" düğmesiyle kontrol et.

Güvenlik
  * Uygulama yalnızca bu bilgisayarda (127.0.0.1) dinler; internete açık değildir.
  * Bir web sayfası uygulamaya indirme başlatamaz: yalnızca tarayıcı EKLENTİLERİNDEN gelen istekler kabul edilir.
  * DISO'yu native messaging ile yalnızca bu eklenti (sabit kimliğiyle) başlatabilir.
  * Uygulamadaki "Tarayıcı eklentisinden link al" anahtarıyla bu özelliği tamamen kapatabilirsin.
