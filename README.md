# ⚡ Hızlı İndirici

IDM / FDM tarzı indirme yöneticisi: **dosya** (parçalı, çok bağlantılı) + **video (MP4)** + **MP3**.

## Kurulum
1. Python 3.10+ kur (kurulumda **"Add Python to PATH"** işaretli olsun).
2. `run.bat` dosyasına çift tıkla → kütüphaneleri kurar ve programı açar.
   (Elle: `pip install -r requirements.txt` sonra `python main.py`)
3. EXE istersen `build.bat` → `dist\HizliIndirici.exe`

**FFmpeg kurman gerekmez:** MP3 veya video+ses birleştirme ilk gerektiğinde program kendisi indirir
(bir kereye mahsus, ~90 MB). İstersen `ffmpeg.exe` ve `ffprobe.exe` dosyalarını `ffmpeg/` klasörüne koy.

## Kullanım
- Linki yapıştır → **⬇ İndir**. "Otomatik" modda program dosya mı video mu kendi anlar.
- Birden fazla linki boşlukla ayırıp yapıştırabilirsin.
- Her satırda ⏸/▶ (duraklat/devam), 📂 (klasörü aç), ✖ (iptal/sil) var. Program kapansa bile yarım indirmeler kaldığı yerden devam eder.
- "Panodaki linkleri otomatik ekle" açıkken kopyaladığın her link listeye eklenir.
- Aynı anda kaç indirme çalışacağını (1–8, varsayılan 3), toplam hız sınırını, bildirimleri ve "tüm indirmeler bitince" eylemini `⚙ Ayarlar` penceresinden seçersin. Diğer indirmeler sırada bekler.
- Seçtiğin klasör, kalite, bağlantı sayısı gibi ayarlar kapanıp açılınca hatırlanır.
- Linki pencereye **sürükle-bırak** yapabilir ya da `📄` düğmesiyle bir `.txt` dosyasındaki tüm linkleri ekleyebilirsin. Listede zaten olan link tekrar eklenmez.
- Listede arama, filtre (aktif, tamamlanan, hatalı…), sıralama ve kutucukla çoklu seçim (toplu başlat/duraklat/sil) var.
- İndirme bitince ses ve Windows bildirimi gelir.

## Testler (geliştirenler için)
`run_tests.bat` (ya da `python -m pytest`) tüm testleri çalıştırır. İnternet gerekmez: testler yerel bir sunucuyla
Range desteği olmayan, bağlantısı kopan, bağlantı sınırı koyan sunucuları ve sahte bir PyPI'yi taklit eder.
Gerçek FFmpeg gerektiren testler `ffmpeg/` klasöründe (veya PATH'te) ffmpeg yoksa, pencere testleri ekran yoksa atlanır.
- Sadece hızlı testler: `python -m pytest -m "not gui and not ffmpeg"`
- Tek dosya: `python -m pytest tests/test_downloader.py`

## Sorun giderme
- **Güncellemeler:** Program her açılışta yt-dlp, yt-dlp-ejs ve FFmpeg'i kontrol eder; yeni sürüm varsa kendisi indirir (SHA-256 ile doğrulanır). Durumu ve elle kontrolü `⟳ Güncellemeler` penceresinden yapabilirsin.
- **YouTube/Instagram aniden çalışmazsa:** `⟳ Güncellemeler` → "Kontrol et" → programı yeniden aç. EXE'de de aynısı geçerli; yt-dlp program içinde güncellenir, `build.bat` gerekmez.
- **YouTube "format bulunamadı" derse:** bir kez `winget install DenoLand.Deno` kur.
- **Giriş isteyen videolar:** "Giriş çerezleri" menüsünden giriş yaptığın tarayıcıyı seç (Firefox en sorunsuzu).
- **Google Drive / Mega / MediaFire sayfaları** doğrudan indirme linki değildir; program bir sayfadaki butona basamaz.

Ayrıntılı teknik açıklama: `HOW_IT_WAS_MADE.txt` (İngilizce)
