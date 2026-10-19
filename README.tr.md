# DISO

**[English](README.md) | Türkçe**

Dosya, video ve müzik indirme yöneticisi, yanında bir müzik çalar. Windows için. **Sürüm 0.10.1 beta**: her şey çalışıyor, bazı yerler hâlâ pürüzlü olabilir. Arayüz **Türkçe ve İngilizce**.

Linki yapıştır, gerisini DISO'ya bırak: **dosya** (parçalı, çok bağlantılı, IDM/FDM gibi), **video (MP4)**, **MP3**, YouTube / Instagram / TikTok / X ve daha fazlası.

## Kurulum (Python'u olmayan bir bilgisayar için)
`DISO-Kurulum-0.10.1-beta.exe` dosyasına çift tıkla, **Kur**'a bas. Python, FFmpeg, yt-dlp ve YouTube için gereken Deno paketin içinde, ayrıca bir şey kurman gerekmez.
- **Yönetici izni ister:** DISO bu bilgisayardaki herkes için `C:\Program Files\ISO\DISO` klasörüne kurulur. Windows "izin ver?" diye sorar, **Evet** de.
- Başlat menüsüne ve masaüstüne kısayol koyar, "Uygulamalar" listesine yazılır. İstersen Windows ile birlikte başlar.
- **Güncelleme:** yeni kurulum dosyasını çalıştırman yeter. Çalışan DISO'yu kapatır, aynı klasöre kurar; ayarların ve çalma listelerin korunur.
- **Eski sürümden geliyorsan** (Hızlı İndirici): kurulum eskisini kendisi kaldırır, ayarların, çalma listelerin ve indirme listen `%LOCALAPPDATA%\DISO` klasörüne taşınır, hiçbir şey kaybolmaz.
- **Kaldırma:** Ayarlar → Uygulamalar → DISO → Kaldır (ya da Başlat menüsündeki "DISO'yu Kaldır"). Yalnızca kurulumun koyduklarını siler. Ayarlarını, çalma listelerini ve müzik çalardan bulup indirdiğin şarkıları da silmek isteyip istemediğini sorar. İndirme klasörüne indirdiklerine dokunmaz.
- **Sessiz kurulum:** `DISO-Kurulum-0.10.1-beta.exe --silent [--dir "C:\yol"] [--no-desktop] [--autostart]` ve `Uninstall.exe --silent [--remove-data]`. Günlük: `%TEMP%\DISO-kurulum.log`.
- Windows "bilinmeyen yayıncı" uyarısı çıkarabilir (paket dijital olarak imzalı değil): **Daha fazla bilgi → Yine de çalıştır**.

## 🌐 Dil
DISO, kurulum programı ve tarayıcı eklentisi **Türkçe ve İngilizce** konuşur. İlk açılışta Windows Türkçe ise Türkçe, değilse İngilizce başlar. Sonra istediğin zaman değiştirebilirsin: Ayarlar → **Dil** (DISO yeniden açılır). Kurulum ve kaldırma pencereleri DISO'da seçtiğin dili kullanır; tarayıcı eklentisi tarayıcının dilini.

## Geliştirici kurulumu
1. Python 3.10+ kur (kurulumda **"Add Python to PATH"** işaretli olsun).
2. `run.bat` dosyasına çift tıkla: kütüphaneleri kurar ve programı açar. (Elle: `pip install -r requirements.txt` sonra `python main.py`)
3. Tek dosyalık, kurulumsuz taşınabilir `DISO.exe` için `build.bat` (daha küçüğü için `build.bat --no-ffmpeg`). Her açılışta kendini geçici klasöre açtığı için açılması birkaç saniye sürer.
4. Kurulum paketi için `python tools/build_installer.py`: programı klasör halinde derler (`build\app\DISO`, `python tools/build_exe.py --onedir`), Deno'yu indirip SHA-256 ile doğrular ve `dist\DISO-Kurulum-<sürüm>.exe` çıkarır. Kurulan DISO bir klasör olduğu için her açılışta açılmayı beklemez, 2–3 saniyede açılır.
5. İkonlar tek bir resimden üretilir: `IKON\icon.png` değişince `python tools/make_icons.py`.

İsim, yayıncı, sürüm ve GitHub adresi tek yerde: `app/brand.py`. Arayüzün İngilizcesi `app/lang_en.py`'de (anahtarlar ekrandaki Türkçe metinler).

**FFmpeg kurman gerekmez:** MP3 veya video+ses birleştirme ilk gerektiğinde DISO kendisi indirir (bir kereliğine, ~115 MB, SHA-256 ile doğrulanır). İstersen `ffmpeg.exe` ve `ffprobe.exe` dosyalarını `ffmpeg/` klasörüne koy.

## Kullanım
- Linki yapıştır, **⬇ İndir**'e bas. "Otomatik" modda DISO dosya mı video mu kendi anlar.
- `📄` ile bir `.txt` dosyasındaki bütün linkleri ekleyebilir, `Ctrl+V` ile panodaki linkleri listeye atabilirsin. Listede zaten olan link tekrar eklenmez.
- **ℹ** düğmesi bir linkin kalitelerini, boyutlarını ve altyazı dillerini gösterir; istediğin kaliteyle ya da MP3 olarak tek tıkla indirirsin.
- **Oynatma listesi** kutusu işaretliyken bir liste linki eklersen hangi videoların inecek olduğunu seçebilirsin.
- **Altyazı** menüsü (Türkçe / İngilizce / tüm diller) altyazıyı videonun yanına `.srt` olarak kaydeder ve MP4'ün içine de koyar (oynatıcıda altyazı seçeneği olarak çıkar). YouTube bazen kendi çevirisini (ör. İngilizceden Türkçeye) vermez; o zaman videonun kendi dilindeki altyazıyı kaydeder ve bunu satırda söyler. Altyazı alınamasa bile video her zaman iner. MP3'lere videonun küçük resmi **kapak resmi** olarak gömülür.
- **Türe göre klasör** kutusu dosyaları Video, Müzik, Arşiv, Belge, Program, Resim, Diğer klasörlerine ayırır.
- Her satırda ⏸/▶ (duraklat/devam), 📂 (klasörü aç), ✖ (kaldır) var; **sağ tık** menüsü ve çift tıkla açma da. DISO kapansa bile yarım indirmeler kaldığı yerden devam eder. Satırın solundaki renkli şerit durumu gösterir (iniyor, bitti, hata, beklemede).
- Listede arama, filtre, sıralama ve kutucukla çoklu seçim (toplu başlat/duraklat/sil) var. Kısayollar: `Ctrl+F` ara, `Ctrl+A` hepsini seç, `Delete` seçilenleri sil.
- Bağlantı koparsa indirme **kendi kendine tekrar dener** (10, 30, 60 sn… artan beklemeyle) ve kaldığı yerden sürer.
- İndirme bitince ses ve Windows bildirimi gelir.

### 🎵 Müzik çalar modu
Pencerenin en altındaki **İndirme modu | Müzik çalar modu** anahtarıyla ayrı bir müzik çalar penceresine geçersin; indirmeler arkada sürer, müzik de pencere değişse kesilmez.
- **Birden fazla çalma listesi** yapabilirsin (`＋` yeni, `✎` ad değiştir, `🗑` sil). Listeler kapanınca kaybolmaz (`%LOCALAPPDATA%\DISO\playlists.json`).
- `＋ Dosya` ve `📁 Klasör` ile müzik eklersin; parçaları `▲` `▼` (ya da `Ctrl+↑/↓`) ile istediğin sıraya dizersin, `Delete` ile çıkarırsın. Dosyalar silinmez.
- Çift tıklayınca o parçadan başlar. Çal/duraklat, önceki/sonraki, ilerleme çubuğu, ses, **🔀 Karışık** ve **🔁 Tekrar** (kapalı / liste / tek) var. `Boşluk` çal/duraklat.
- Parça tablosunda **sanatçı, başlık ve süre** görünür (dosyanın etiketlerinden, arka planda okunur; etiketi olmayan dosya adıyla görünür). Listenin toplam süresi altta yazar. Çalan parçanın **kapak resmi** ve albümü çalar kutusunda görünür.
- Biten müzik indirmeleri **kendiliğinden çalma listesine girer**: YouTube oynatma listesi kendi adıyla bir listeye (sırası korunarak), tek başına inen MP3 "İndirilenler" listesine. Kapatmak için Ayarlar → "Biten müzikleri çalma listesine ekle". Bir indirmenin **sağ tık menüsünden → Müzik listesine ekle** ile istediğin listeye de koyabilirsin.
- **Dosyası silinen parça listeden kendiliğinden çıkar** (altta kısa bir not düşer). Takılı olmayan bir USB bellekteki parça silinmiş sayılmaz, bellek takılınca yerinde durur.
- **Listede ara** (`Ctrl+F`): yazdıkça süzer. **Sütun başlığına tıkla**, liste o sütuna göre sıralanır (ikinci tık tersten).
- **Sağ tık:** çal, klasörde göster, başka listeye ekle, listeden çıkar.
- **Kaldığın yerden devam:** DISO'yu kapatıp açınca son çalan şarkı "Kaldığın yer" diye görünür, ▶ ile aynı saniyeden sürer.
- **⏭ Sıradaki olarak çal / ➕ Sıraya ekle** (sağ tık): listeyi bozmadan, istediğin şarkıları şu ankinden sonra çaldırır; **📋 Sıra** düğmesi sırayı gösterir (tıkla: çıkar, ya da hepsini temizle).
- **🎚 Şarkılar arası geçiş** (⚙ menüsü): biten şarkı kısılırken yenisi 3, 6 ya da 10 saniyede yavaşça girer.
- **🗗 Mini oynatıcı**: köşede her zaman üstte duran küçük çalar (kapak, ⏮ ⏯ ⏭, ilerleme); ⤢ ile büyük pencereye dönülür.
- **Görev çubuğu ve Windows ses paneli**: müzik penceresinin görev çubuğu önizlemesinde ⏮ ⏯ ⏭; ses tuşlarına basınca çıkan Windows panelinde çalan şarkı, sanatçı ve kapak, düğmeleriyle.
- **🔀 Karıştır** düğmesi listeye kalıcı olarak yeni bir rastgele sıra verir (beğenmezsen `Ctrl+Z` eski sıraya döndürür). Sırayı bozmadan karışık dinlemek istersen oynatıcıdaki **🔀 Karışık** kutusunu kullan.
- **🎤 Şarkı sözleri:** çalan (ya da seçtiğin) şarkının sözü varsa oynatıcının sağ üstünde **🎤 Sözler** düğmesi çıkar, yoksa hiç görünmez. Sözler penceresinde zamanlı sözler şarkıyla birlikte akar: söylenen satır büyük ve renkli, bir satıra tıklarsan şarkı oraya atlar; yazıyı A−/A+ ile büyütüp küçültebilirsin. Sözler önce **YouTube Music**'ten gelir (DISO'dan inen şarkıda o videonun kendi sözleri, diğerlerinde ad ve sanatçıyla aranır); satır zamanları YouTube Music'te yoksa [LRCLIB](https://lrclib.net)'ten alınır, ama yalnızca metni aynı şarkıysa. Şarkının yanına `şarkı.lrc` olarak kaydedilir. Yanlış gelirse sağ tık → "🔄 Sözler yanlış, yeniden bul" ya da sözler penceresindeki "Yanlışsa yeniden bul". "Şarkı bul" ile indirdiğin şarkıların sözleri kendiliğinden aranır; başka bir şarkı için sağ tık → "Şarkı sözlerini internette bul".
- **😴 Uyku zamanlayıcısı:** 15–90 dakika sonra ya da çalan parça bitince müziği durdurur.
- **Klavyedeki medya tuşları** (çal/duraklat, ileri, geri, durdur) DISO öndeyken de arkadayken de çalışır. Tuşları yalnızca müzik çalarken (ya da duraklatılmışken) alır; durdurunca tarayıcıya ve diğer programlara geri bırakır.
- Desteklenen biçimler Windows'un çalabildikleridir: mp3, wav, wma, m4a, aac. Windows'un doğrudan açamadığı dosyaların (kapak resmi büyük MP3'ler, Opus sesli videolar) çalınabilir bir kopyası ilk çalışta arka planda hazırlanır.

#### 🔍 Şarkı bul
Müzik çaların üstündeki **🔍 Şarkı bul** sekmesine şarkı ya da sanatçı adı yaz (YouTube linki de olur), Enter'a bas. Sonuçlarda başlık, kanal ve süre görünür.
- Beğendiğine **çift tıkla** ya da seçip **⬇ İndir (MP3)**'e bas. Şarkı arka planda MP3 olarak (kapak resmiyle) iner, sen bu arada dinlemeye devam edersin. Ekranda yalnızca yüzdesi görünür.
- İnince **"Hangi listeye ekleyeyim?"** diye sorar: var olan bir liste, yeni bir liste ya da "Şimdilik ekleme". Aynı anda biten şarkılar için tek soru gelir; son seçtiğin liste bir dahaki sefere önce önerilir.
- Bulup indirdiğin şarkılar `%LOCALAPPDATA%\DISO\Müzik` klasöründe durur (**📂 İnenler** düğmesi açar). İndirme listesinde de görünürler, oradan duraklatıp sürdürebilirsin.
- **🎧 Önizle**: indirmeden önce şarkının 30 saniyesini dinle (çalan müzik bekler, sonra kaldığı yerden devam eder).
- Yazarken **YouTube önerileri** ve **son aramaların** çıkar; ↑ ↓ ve Enter ile seçersin.
- **YouTube Music / YouTube listesi linki** yapıştırırsan şarkıları gelir; **⬇ Hepsini indir** hepsini MP3 olarak indirip listenin adıyla bir çalma listesine, sırasıyla koyar.
- Aynı şarkıyı iki kez indirmez: iniyorsa bekler, inmişse yeniden listeye eklemeyi sorar, yarım kaldıysa kaldığı yerden sürer.

### ⚙ Ayarlar
Aynı anda indirme sayısı (1–8), toplam **hız sınırı**, otomatik deneme sayısı, **proxy** (http / socks5, "Dene" düğmesiyle), bildirimler, **zamanlayıcı**, **kapatınca arka planda çalış** (sistem tepsisi), **Windows ile başlat**, tema (koyu/açık/sistem), görünüm stili (Yeni/Klasik), **dil** (Türkçe/English), "tüm indirmeler bitince" eylemi (DISO'yu kapat / uyut / bilgisayarı kapat) ve günlük dosyası. Seçtiğin her şey kapanıp açılınca hatırlanır.

**Yedek ve yardım:** 💾 Yedek al (ayarlar, çalma listeleri, indirme listesi ve geçmiş tek `.disoyedek` dosyasına), 📂 Yedeği yükle (başka bilgisayardan getir), 📊 İndirme geçmişi (ne zaman ne indi, ne kadar hızlı, en çok hangi siteden; listeden silinenler de kalır), ⌨ Klavye kısayolları (her yerde **F1**).

**ℹ Hakkında** (Ayarlar'da, ya da başlıktaki BETA rozetine tıkla): sürümü, DISO'nun nerede durduğunu ve verilerinin nerede olduğunu gösterir. **📋 Detayları kopyala** sürüm, Windows, yt-dlp, FFmpeg ve Deno bilgilerini tek seferde panoya alır, **✉ Bize ulaş** GitHub'da yeni bir sorun sayfası açar.

### ⏰ Zamanlayıcı (gece indirme)
Ayarlar → Zamanlayıcı'yı aç, başlangıç (ve istersen bitiş) saatini yaz, örneğin `02:00`–`07:00`. Saat gelene kadar yeni indirmeler sırada bekler. Bitiş saati gelince çalışanlar duraklar, bir sonraki başlangıçta kaldığı yerden devam eder.

## 🧩 Tarayıcı eklentisi
`browser_extension` klasörü Chrome / Edge / Brave / Firefox için eklentidir (kurulum: `browser_extension/README.txt`). Bağlantıya sağ tık → "DISO ile indir"; istersen tarayıcının kendi indirmelerini de yakalar (DISO kapalıysa tarayıcı normal indirir). Giriş gerektiren siteler için tarayıcının oturumu DISO'ya iletilir (çerezler diske yazılmaz). DISO yalnızca bu bilgisayarda dinler ve web sayfalarından değil, yalnızca **eklentiden** gelen istekleri kabul eder. Eklenti tarayıcının diline göre Türkçe ya da İngilizce görünür.

## Testler (geliştirenler için)
`run_tests.bat` (ya da `python -m pytest`) tüm testleri çalıştırır. İnternet gerekmez: testler yerel bir sunucuyla Range desteği olmayan, bağlantısı kopan, bağlantı sınırı koyan sunucuları, sahte bir proxy'yi ve sahte bir PyPI'yi taklit eder. Eklentinin mantığı `node` ile de sınanır. İngilizce arayüz ve İngilizce kurulum ayrı bir süreçte gerçekten açılıp ekranda Türkçe yazı kalmadığı denetlenir. Gerçek FFmpeg gerektiren testler `ffmpeg/` klasöründe (veya PATH'te) ffmpeg yoksa, pencere testleri ekran yoksa, eklenti testleri node yoksa atlanır. Kurulum paketi testleri (`-m installer`) paket derlenmişse gerçek `Kurulum.exe`'yi geçici bir yerde çalıştırır, gerçek Başlat menüne ya da kayıt defterine dokunmaz.
- Sadece hızlı testler: `python -m pytest -m "not gui and not ffmpeg and not exe and not installer"`
- Tek dosya: `python -m pytest tests/test_downloader.py`
- Kurulumu pencere açmadan denetle: `python main.py --selftest sonuc.json`

## Sorun giderme
- **Güncellemeler:** DISO her açılışta yt-dlp, yt-dlp-ejs ve FFmpeg'e bakar; yeni sürüm varsa kendisi indirir (SHA-256 ile doğrulanır). Yeni yt-dlp çalışmazsa otomatik olarak öncekine dönülür. Durumu ve elle kontrolü `⟳ Güncellemeler` penceresinden yapabilirsin.
- **YouTube/Instagram aniden çalışmazsa:** `⟳ Güncellemeler` → "Kontrol et" → DISO'yu yeniden aç. yt-dlp program içinde güncellenir, yeniden derlemek gerekmez.
- **YouTube "format bulunamadı" derse:** kurulum paketiyle gelen Deno yeterlidir. Kaynak koddan çalıştırıyorsan bir kez `winget install DenoLand.Deno` kur.
- **Giriş isteyen videolar:** "Giriş çerezleri" menüsünden giriş yaptığın tarayıcıyı seç (Firefox en sorunsuzu) ya da tarayıcı eklentisini kullan.
- **Google Drive / Mega / MediaFire sayfaları** doğrudan indirme linki değildir; DISO bir sayfadaki butona basamaz.

## ✉ Bize ulaş
Bir hata mı buldun, bir fikrin mi var? [GitHub'da yeni bir sorun aç](https://github.com/muslimekc2112/DISO/issues/new), Türkçe ya da İngilizce yazabilirsin. Hata bildiriyorsan önce DISO'da Ayarlar → **ℹ Hakkında** → **📋 Detayları kopyala**'ya bas ve çıkan metni sorunun içine yapıştır; **✉ Bize ulaş** düğmesi aynı sayfayı açar. Günlük dosyası da işe yarar: `%LOCALAPPDATA%\DISO\diso.log`.

Ayrıntılı teknik açıklama: `NASIL_YAPILDI.txt` (İngilizcesi `HOW_IT_WAS_MADE.txt`). Sürüm geçmişi: [`CHANGELOG.tr.md`](CHANGELOG.tr.md). Lisans: MIT (`LICENSE`).
