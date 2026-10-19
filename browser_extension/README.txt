DISO — BROWSER EXTENSION / TARAYICI EKLENTİSİ
=============================================

(Türkçesi aşağıda.)

ENGLISH
-------

What does it do?
  * Right-click a link -> "Download with DISO"
  * Right-click a video / sound / picture -> the same menu
  * Right-click the page -> "Download this page with DISO (video)"
  * Select text and right-click -> every link in the selection
  * If you like, it catches the browser's own downloads and hands them to the app
    (switched on in its settings; if the app is closed, the browser downloads as usual).
  * For sites that need a login, the browser's session (cookies, page address) is passed to the app.
    Cookies are never written to disk; they are kept in memory only while the download runs.
  * It speaks English or Turkish, following the browser's language.

Installing — Chrome / Edge / Brave
  1. Type  chrome://extensions  (Edge: edge://extensions) in the address bar.
  2. Turn on "Developer mode" at the top right.
  3. "Load unpacked" -> choose this folder (browser_extension).

Installing — Firefox
  1. Type  about:debugging#/runtime/this-firefox  in the address bar.
  2. "Load Temporary Add-on" -> choose the manifest.json file in this folder.
     (Firefox removes temporary add-ons when it closes; a lasting install needs a signed add-on.)

Using it
  * The DISO app must be OPEN.
  * The port must be the same as Settings -> "Extension port" in the app (default 17653).
    Check it with the "Test the connection" button on the extension's settings page.

Safety
  * The app listens only on this PC (127.0.0.1); it is not open to the internet.
  * A web page cannot start a download in the app: only requests from browser EXTENSIONS are accepted.
  * The "Take links from the browser extension" switch in the app turns this feature off completely.


TÜRKÇE
------

Ne yapar?
  * Bağlantıya sağ tık -> "DISO ile indir"
  * Videonun / sesin / resmin üstüne sağ tık -> aynı menü
  * Sayfaya sağ tık -> "Bu sayfayı DISO ile indir (video)"
  * Metin seçip sağ tık -> seçilen bağlantıların hepsi
  * İstersen tarayıcının kendi indirmelerini yakalar ve uygulamaya yönlendirir
    (Ayarlar'dan açılır; uygulama kapalıysa tarayıcı normal indirir).
  * Giriş gerektiren siteler için tarayıcının oturumu (çerez, sayfa adresi) uygulamaya iletilir.
    Çerezler diske yazılmaz, yalnızca indirme sürerken bellekte tutulur.
  * Tarayıcının diline göre Türkçe ya da İngilizce konuşur.

Kurulum — Chrome / Edge / Brave
  1. Adres çubuğuna  chrome://extensions  (Edge: edge://extensions) yaz.
  2. Sağ üstten "Geliştirici modu"nu aç.
  3. "Paketlenmemiş öğe yükle" -> bu klasörü (browser_extension) seç.

Kurulum — Firefox
  1. Adres çubuğuna  about:debugging#/runtime/this-firefox  yaz.
  2. "Geçici eklenti yükle" -> bu klasördeki manifest.json dosyasını seç.
     (Firefox geçici eklentileri kapanınca siler; kalıcı kurulum için eklenti imzalanmalıdır.)

Kullanım
  * DISO uygulaması AÇIK olmalı.
  * Bağlantı noktası uygulamadaki Ayarlar -> "Eklenti bağlantı noktası" ile aynı olmalı (varsayılan 17653).
    Eklentinin ayar sayfasındaki "Bağlantıyı dene" düğmesiyle kontrol et.

Güvenlik
  * Uygulama yalnızca bu bilgisayarda (127.0.0.1) dinler; internete açık değildir.
  * Bir web sayfası uygulamaya indirme başlatamaz: yalnızca tarayıcı EKLENTİLERİNDEN gelen istekler kabul edilir.
  * Uygulamadaki "Tarayıcı eklentisinden link al" anahtarıyla bu özelliği tamamen kapatabilirsin.
