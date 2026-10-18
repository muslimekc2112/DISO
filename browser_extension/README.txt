HIZLI İNDİRİCİ — TARAYICI EKLENTİSİ
====================================

Ne yapar?
  * Bağlantıya sağ tık -> "DISO ile indir"
  * Videonun / sesin / resmin üstüne sağ tık -> aynı menü
  * Sayfaya sağ tık -> "Bu sayfayı DISO ile indir (video)"
  * Metin seçip sağ tık -> seçilen bağlantıların hepsi
  * İstersen tarayıcının kendi indirmelerini yakalar ve uygulamaya yönlendirir
    (Ayarlar'dan açılır; uygulama kapalıysa tarayıcı normal indirir).
  * Giriş gerektiren siteler için tarayıcının oturumu (çerez, sayfa adresi) uygulamaya iletilir.
    Çerezler diske yazılmaz, yalnızca indirme sürerken bellekte tutulur.

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
