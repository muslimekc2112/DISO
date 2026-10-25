<div align="center">

<img src="assets/icon.png" alt="DISO" width="112">

# DISO

**Dosya, video ve müzik indirme yöneticisi; içinde tam donanımlı bir müzik çalar.**

[![Son sürüm](https://img.shields.io/github/v/release/muslimekc2112/DISO?label=s%C3%BCr%C3%BCm&color=2ea44f)](https://github.com/muslimekc2112/DISO/releases/latest)
[![İndirme](https://img.shields.io/github/downloads/muslimekc2112/DISO/total?label=indirme&color=blue)](https://github.com/muslimekc2112/DISO/releases)
![Windows 10 | 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Türkçe | English](https://img.shields.io/badge/dil-T%C3%BCrk%C3%A7e%20%7C%20English-e30a17)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-yellow)](LICENSE)

**[English](README.md) | Türkçe**

### [⬇ Son sürümü indir](https://github.com/muslimekc2112/DISO/releases/latest)

</div>

---

Linki yapıştır, gerisini DISO'ya bırak: parçalara bölünüp çok bağlantıyla inen **dosyalar** (IDM / FDM gibi), **MP4 video**, **MP3 müzik**; YouTube, Instagram, TikTok, X ve daha pek çok siteden. Üstüne **torrent**. Tek tıkla **müzik çalara** geç: çalma listeleri, şarkı sözleri, ekolayzır, görselleştirici ve doğrudan YouTube Music'ten bulup indirdiğin şarkılar. **Tarayıcı eklentisi** linkleri, bütün bir diziyi ve herhangi bir sitede oynayan videoları DISO'ya gönderir.

## İçindekiler
- [Neler yapar](#-neler-yapar)
- [Kurulum](#-kurulum)
- [İndirme](#-i̇ndirme)
- [Müzik çalar](#-müzik-çalar)
- [Tarayıcı eklentisi](#-tarayıcı-eklentisi)
- [Ayarlar](#-ayarlar)
- [Dil](#-dil)
- [Yenilikler](#-yenilikler)
- [Sorun giderme ve sorular](#-sorun-giderme-ve-sorular)
- [Geliştirenler için](#-geliştirenler-için)
- [Bize ulaş](#-bize-ulaş)

## ✨ Neler yapar

| | |
|---|---|
| ⚡ **Hızlı indirme** | Dosyalar parçalara bölünüp aynı anda çok bağlantıyla iner. Yarım kalan indirmeler DISO kapanıp açılsa bile kaldığı yerden sürer; bağlantı koparsa kendi kendine yeniden dener. |
| 🎬 **Video ve MP3** | YouTube, Instagram, TikTok, X ve yt-dlp'nin tanıdığı daha pek çok site. Kaliteyi seç, videonun yalnız bir kısmını indir, altyazı al, kapak resimli MP3 yap. |
| 🎞 **Her siteden video** | Tarayıcı eklentisi sayfada oynayan videoları (HLS / DASH akışları dahil) yakalar; DISO'nun kendisinin okuyamadığı sitelerde bile. **Dizi modu** bütün bir diziyi bölüm bölüm indirir. |
| 🧲 **Torrent** | Magnet linkleri ve `.torrent` dosyaları; hangi dosyaların ineceğini sen seçersin. |
| 🎵 **Müzik çalar** | Çalma listeleri, boşluksuz geçiş, dalga ilerleme çubuğu, şarkıyla akan sözler, 8 bantlı ekolayzır, çalma hızı ve perde, görselleştirici, mini oynatıcı. |
| 🔍 **Şarkı bul** | DISO'nun içinden YouTube Music'te ara, 30 saniye önizle, MP3 olarak doğrudan çalma listesine indir. |
| 🛡 **Güvenli** | Biten her indirme Windows Defender ile taranır. Güncellemeler SHA-256 ile doğrulanır. Sen istemeden hiçbir şey inmez. |
| 🕹 **Senin görünümün** | **Standart** (önerilen: modern, düğmelerde renkli resimler), Yeni, Klasik ya da **Nostalji** (2000'lerin gri indirme yöneticileri); kendi vurgu rengin, koyu ya da açık, Türkçe ya da İngilizce. |

## 📥 Kurulum

**Gerekenler:** Windows 10 ya da 11. Başka hiçbir şey: Python, FFmpeg, yt-dlp ve YouTube için gereken Deno paketin içinde.

1. [Son sürüm](https://github.com/muslimekc2112/DISO/releases/latest) sayfasından **`DISO-Setup-<sürüm>.exe`** dosyasını indir.
2. Çift tıkla, **Kur**'a bas. Windows yönetici izni ister, **Evet** de. DISO bu bilgisayardaki herkes için `C:\Program Files\ISO\DISO` klasörüne kurulur.
3. Kurulum **hangi tarayıcılara eklenti kurulacağını** sorar ve eklemene yardım eder (bkz. [Tarayıcı eklentisi](#-tarayıcı-eklentisi)).

Kurulum Başlat menüsüne ve masaüstüne kısayol koyar, Windows'un "Uygulamalar" listesine yazılır ve istersen DISO'yu Windows ile birlikte başlatır.

> **"Windows bilgisayarınızı korudu" / "bilinmeyen yayıncı" mı çıktı?** Paket dijital olarak imzalı olmadığı için Windows uyarır. **Daha fazla bilgi → Yine de çalıştır**'a bas.

- **🔄 Güncelleme:** DISO yeni sürüm çıkınca haber verir. `⟳ Güncellemeler` → **DISO** → **Güncelle** kurulum dosyasını indirir, SHA-256 ile doğrular ve kurar (Windows izin ister), sonra DISO yeni sürümle açılır. Sen istemeden hiçbir şey inmez. Yeni kurulum dosyasını elle çalıştırmak da olur: çalışan DISO'yu kapatır, aynı klasöre kurar. Ayarların ve çalma listelerin korunur.
- **Eski sürümden geliyorsan (Hızlı İndirici):** kurulum eskisini kendisi kaldırır; ayarların, çalma listelerin ve indirme listen `%LOCALAPPDATA%\DISO` klasörüne taşınır. Hiçbir şey kaybolmaz.
- **Kaldırma:** Ayarlar → Uygulamalar → DISO → Kaldır, ya da Başlat menüsünde DISO'ya sağ tık → Kaldır, ya da Başlat menüsündeki "DISO'yu Kaldır". Yalnızca kurulumun koyduklarını siler. Ayarlarını, çalma listelerini ve müzik çalardan bulduğun şarkıları da silmek isteyip istemediğini sorar. İndirme klasörüne indirdiklerine **asla** dokunmaz.
- **Sessiz kurulum:** `DISO-Setup-<sürüm>.exe --silent [--dir "C:\yol"] [--no-desktop] [--autostart]`; kaldırmak için `DISO.exe --uninstall --silent [--remove-data]` (kurulum klasöründeki DISO.exe). Günlük: `%TEMP%\DISO-kurulum.log`.

## 🚀 İndirme

### Temeller
- Linki yapıştır, **⬇ İndir**'e bas. **Otomatik** modda DISO dosya mı video mu kendisi anlar.
- `📄` bir `.txt` dosyasındaki bütün linkleri ekler; `Ctrl+V` panodaki linkleri listeye atar. Listede zaten olan link tekrar eklenmez.
- **📋 Panoyu izle** açıkken bir link kopyalayınca köşede küçük bir pencere sorar: **⬇ İndir**, **🎬 MP4**, **🎵 MP3** ya da **Hayır** (DISO sistem tepsisindeyken de).
- Her satırda ⏸ / ▶ (duraklat / devam), 📂 (klasörü aç) ve ✖ (kaldır), **sağ tık** menüsü ve çift tıkla açma var. Soldaki renkli şerit durumu gösterir: iniyor, bitti, hata, beklemede.
- Listede arama, filtre, sıralama ve birden çok satırla birlikte çalışmak için kutucuklar var. `Ctrl+F` ara, `Ctrl+A` hepsini seç, `Delete` seçilenleri sil.
- **⏫ En üste al:** bekleyen bir indirmeye sağ tık, sıradaki o olur.
- **📈 Hız grafiği:** listenin altında son bir dakikanın hızı (Nostalji'de siyah üstüne yeşil; her indirmenin ilerleme penceresinde de).
- **Türe göre klasör** dosyaları Video, Müzik, Arşiv, Belge, Program, Resim ve Diğer klasörlerine ayırır.
- İndirme bitince ses ve Windows bildirimi (DISO'nun adı ve simgesiyle) gelir.

### Video ve müzik
- **ℹ** düğmesi bir linkin kalitelerini, boyutlarını ve altyazı dillerini gösterir; istediğin kaliteyle ya da MP3 olarak tek tıkla indirirsin.
- **✂ Sadece bir kısmını indir:** ℹ penceresinde **Başlangıç** ve **Bitiş** yaz (`1:30`, `1:02:03` ya da saniye). Yalnızca o kısım iner, `Ad [1.30–2.45].mp4` gibi kaydedilir.
- **Oynatma listeleri:** **Oynatma listesi** işaretliyken bir liste linki eklersen hangi videoların ineceğini seçersin.
- **Altyazı** (Türkçe / İngilizce / tüm diller) videonun yanına `.srt` olarak kaydedilir ve MP4'ün içine altyazı seçeneği olarak konur. YouTube kendi çevirisini vermezse videonun kendi dilindeki altyazı kaydedilir ve satırda yazar. Altyazı alınamasa bile video her zaman iner.
- MP3'lere videonun küçük resmi **kapak resmi** olarak gömülür.
- **📺 Kanal takibi** (link satırındaki 📺): bir kanalın linkini, `@kanaladı`nı ya da bir videosunu yapıştırıp **Takip et**. DISO kanallara arada bir bakar (30 dakikada bir … günde bir) ve yeni video gelince **bildirim** verir. **Hiçbir şeyi kendiliğinden indirmez:** istediğini **MP4** ya da **MP3** indirirsin, gerisini **Gördüm** ile kaldırırsın.
- **Duran akış devam eder:** duraklatılan ya da DISO kapanınca yarım kalan HLS / DASH indirmesi elindeki parçaları saklar ve oradan sürer.

### Torrent
- **Magnet linki**, `.torrent` linki ya da `📄` ile `.torrent` dosyası ekle. İşi aria2 yapar; ilk torrentte bir kereliğine indirilir (~2.5 MB, SHA-256 ile doğrulanır).
- **🧲 Dosyaları seç:** çok dosyalı bir torrent başlamadan önce klasör ağacından istediklerini seçersin (Hepsi / Videolar / Müzik …); seçilen boyut ve diskteki boş yer görünür. İnerken sağ tık → **Dosyaları seç…** ile değiştirilir.
- Biten torrent paylaşılmaya devam etmez; DISO bir indiricidir.

### Güvenlik ve onarım
- **🛡 Her indirmede Windows Defender:** biten her indirme (torrent klasörleri dahil) taranır, sonuç altında yazar: "🛡 Windows Defender: temiz" ya da "⚠ tehdit buldu ve karantinaya aldı". Başka bir antivirüs yüzünden Defender kapalıysa DISO bunu da söyler.
- **🔧 Dosyayı kontrol et / onar** (biten indirmeye sağ tık): yalnızca sonu eksikse sadece eksik kısmı indirir; bozuk dosya baştan indirilebilir.
- **🩺 Sağlık kontrolü** (Ayarlar → Yedek ve yardım): internet, YouTube, GitHub, yt-dlp, FFmpeg, Deno, aria2, eklenti, indirme klasörü ve proxy tek tek denenir; düzeltilebilenin yanında bir düzeltme düğmesi çıkar.
- **🐞 Sorun bildir:** ayrıntıları bir zip'e koyar ve GitHub'da yeni bir sorun sayfası açar. Çalma listeleri, geçmiş, çerezler ve şifreler asla içinde olmaz.

### ⏰ Zamanlayıcı (gece indirme)
Ayarlar → **Zamanlayıcı**'yı aç, başlangıç (ve istersen bitiş) saatini yaz, örneğin `02:00`–`07:00`. Yeni indirmeler başlangıç saatine kadar bekler; bitiş saati gelince çalışanlar duraklar, bir sonraki başlangıçta sürer.

## 🎵 Müzik çalar

Pencerenin en altındaki **İndirme modu | Müzik çalar modu** anahtarı müzik çaları açar; geçiş bir pencereden ötekine yumuşakça solarak olur. İndirmeler arkada sürer, müzik de pencere değişince kesilmez.

### Çalma
- Bir şarkıya çift tıkla, oradan başlar. Çal / duraklat, önceki / sonraki, ses, **🔀 Karışık** ve **🔁 Tekrar** (kapalı / liste / tek). `Boşluk` çalar / duraklatır.
- **〰 İlerleme çubuğu şarkının dalgası:** yüksek yerler uzun, sessiz yerler kısa çubuklar. Tıkla ya da sürükle, oraya atlar; üzerine gelince saniyeyi yazar.
- **⏭ Şarkılar arasında boşluk yok:** sonraki şarkı ikinci bir çalarda hazır bekler, çalan biter bitmez başlar.
- **⏪5 / 5⏩** ve **← / →** 5 saniye geri / ileri sarar (basılı tutunca devam eder). **↑ / ↓** sesi açar / kısar, basılı tutunca hızlanır.
- **⏩ Çalma hızı** (`1x` düğmesi): 0.25x'ten 4x'e, **perde** ±6 yarım ses; ses temiz kalır.
- **🎛 Ekolayzır:** 8 bant (60 Hz – 15 kHz) ve hazır ayarlar (Bas güçlü, Tiz güçlü, Vokal, Pop, Rock, Elektronik, Hip-hop, Klasik müzik, Akustik, Gece). Düz bırakırsan ses hiç değişmez.
- **🎚 Şarkılar arası geçiş:** biten şarkı kısılırken yenisi 3, 6 ya da 10 saniyede yavaşça girer.
- **🔊 Ses seviyesini eşitle:** her şarkının yüksekliği bir kez ölçülür (EBU R128), şarkılar arasında ses zıplamaz.
- **😴 Uyku zamanlayıcısı:** 15–90 dakika sonra ya da çalan şarkı bitince müzik **yavaşça kısılarak** durur; sesin sonra eskisi gibi kalır.
- **Kaldığın yerden devam:** DISO kapanıp açılınca son şarkı "Kaldığın yer" diye görünür, ▶ aynı saniyeden sürdürür.
- **⏭ Sıradaki olarak çal / ➕ Sıraya ekle** (sağ tık): seçtiğin şarkıları listeyi bozmadan şu ankinden sonra çalar; **📋 Sıra** onları gösterir.
- **Klavyedeki medya tuşları** DISO öndeyken de arkadayken de çalışır; yalnızca müzik çalarken ya da duraklatılmışken. Windows ses paneli ve görev çubuğu önizlemesi şarkıyı, sanatçıyı ve kapağı ⏮ ⏯ ⏭ ile gösterir.
- **🗗 Mini oynatıcı:** köşede her zaman üstte duran küçük bir çalar; ⤢ büyük pencereye döner.

### Görünüm
- **🎨 Müziğin rengi:** çaların bloğu, YouTube'daki ortam ışığı gibi, şarkının her anına göre kapağın renklerinde parlar (⚙ menüsünden kapatılır).
- **🎤 Karaoke** (⚙ menüsü): şarkıcının sesi kısılır (bas korunur), sözler görselleştiricide akar. Kulaklık ya da iki hoparlörle en iyisi.
- **🔗 Listeyi arkadaşına gönder** (⚙ menüsü): `K7P2-QM4X` gibi bir kod ve link alırsın; arkadaşın **📥 Paylaşılan listeyi aç** ile açar, şarkılar MP3 olarak iner.
- **🌌 Görselleştirici:** çubuklar, dalga ya da halka. Halkada kapak ortada ritimle atar; renkler kapaktan gelebilir. Altta ⏮ ⏪5 ⏯ 5⏩ ⏭, tam ekran için **F11**.
- Çalan şarkının **kapak resmi** ve albümü çalarda görünür; şarkı değişince kapak yenisine erir.

### Çalma listeleri
- **İstediğin kadar çalma listesi** yap (`＋` yeni, `✎` ad değiştir, `🗑` sil). `%LOCALAPPDATA%\DISO\playlists.json` içinde saklanır.
- `＋ Dosya` ve `📁 Klasör` ile müzik ekle, `▲` `▼` (ya da `Ctrl+↑/↓`) ile sırala, `Delete` ile çıkar. Dosyaların kendisi asla silinmez.
- Tabloda dosyanın etiketlerinden **sanatçı, başlık ve süre**, altta listenin toplam süresi görünür.
- **⇅ Listeyi sırala:** kendi sıram, son eklenen başta / sonda, A → Z, Z → A (Türk alfabesine göre), en çok dinlenen başta. Kendi sıran hep saklı kalır.
- **🔀 Karıştır** listeye kalıcı olarak yeni bir rastgele sıra verir (`Ctrl+Z` eskisini geri getirir).
- `Ctrl+F` ile **listede ara**; sütun başlığına tıklayınca o sütuna göre sıralanır.
- **✨ Akıllı listeler:** **⭐ En çok dinlenenler**, **🆕 Son eklenenler** ve **💤 Hiç dinlenmeyenler** bütün listelerinden kendiliğinden dolar.
- Biten müzik indirmeleri **kendiliğinden çalma listesine girer**: YouTube oynatma listesi kendi adıyla bir listeye, tek MP3 "İndirilenler"e (Ayarlar → "Biten müzikleri çalma listesine ekle" ile kapatılır).
- Dosyası silinen şarkı listeden kendiliğinden çıkar. Takılı olmayan USB bellekteki şarkı silinmiş sayılmaz.
- **📤 / 📥 .m3u listeleri:** bir listeyi telefon ya da başka çalar için `.m3u8` olarak dışa aktar, ya da `.m3u` / `.m3u8` / `.pls` içe aktar.

### Sözler ve şarkı bilgileri
- **🎤 Şarkı sözleri:** şarkının sözü varsa çalarda **🎤 Sözler** düğmesi çıkar. Zamanlı sözler şarkıyla birlikte akar: söylenen satır büyük ve renkli, bir satıra tıklayınca oraya atlar, A− / A+ yazıyı büyütüp küçültür. Sözler yalnızca **YouTube Music**'ten gelir (DISO'dan inen şarkıda o videonun kendi sözleri, yoksa YouTube Music'te aynı ad ve sanatçıdaki, uzunluğu en yakın şarkı); böylece yalnızca adı aynı olan başka bir şarkının sözleri gelmez. Şarkının yanına `şarkı.lrc` olarak kaydedilir.
- Sözler yanlış mı? Sağ tık → "🔄 Sözler yanlış, yeniden bul". Sözleri **✎ elle yazmak ya da yapıştırmak** da olur.
- **🏷 Şarkı bilgilerini düzenle** (sağ tık): ad, sanatçı, albüm, yıl, tür ve kapak resmi dosyanın içine yazılır; ses yeniden kodlanmaz.
- **🖼 Kapağı internetten bul:** tek bir şarkı için ya da listede kapağı olmayan bütün şarkılar için.
- **✏ Dosya adlarını kalıpla düzenle**, örneğin `{artist} - {title}`; önizleme ve **↶ Geri al** ile.

### 🔍 Şarkı bul
**🔍 Şarkı bul** sekmesine şarkının adını (ya da bir YouTube linkini) yaz, istersen yanına sanatçıyı ekle ve Enter'a bas. Arama yalnızca **YouTube Music**'te yapılır ve yalnızca şarkılar gelir: video, lyrics videosu ya da shorts gelmez. Yazdığına uyan şarkılar en üstte, en çok dinlenen önce.
- Bir şarkıya **çift tıkla** ya da seçip **⬇ İndir (MP3)**'e bas. Sen dinlemeye devam ederken kapağıyla birlikte arkada iner.
- İnince DISO **hangi listeye ekleyeyim** diye sorar. Son seçtiğin liste bir dahaki sefere önce önerilir.
- **🎧 Önizle:** önce 30 saniyesini dinle; şarkının en çok tekrar dinlenen yerinden (genelde nakarat) başlar.
- Yazarken **YouTube önerileri** ve **son aramaların** çıkar.
- **YouTube Music / YouTube listesi linki** yapıştır, **⬇ Hepsini indir** bütün şarkıları MP3 olarak listenin adıyla bir çalma listesine, sırasıyla indirir.
- Aynı şarkı iki kez inmez. Şarkılar `%LOCALAPPDATA%\DISO\Müzik` klasöründe durur (**📂 İnenler** düğmesi açar).

**Biçimler:** mp3, wav, wma, m4a, aac, flac, ogg, opus, aiff, wv, ape, mka.

## 🧩 Tarayıcı eklentisi

**Chrome, Edge, Brave, Opera, Vivaldi** ve Firefox için, IDM'inki gibi.

- **Linke sağ tık → "DISO ile indir":** indirme hemen DISO'da başlar. Video, ses ya da resmin üstünde, seçili metinde (içindeki bütün linkler) ve **"Bu sayfadaki tüm dosya linklerini DISO ile indir"** ile de çalışır.
- **🎞 Her siteden video:** eklenti sayfada oynayan videoları bulur (HLS `.m3u8`, DASH `.mpd`, video ve ses dosyaları; gizli oynatıcıların içindekiler ve `.txt`, `.png` gibi adların arkasına gizlenmiş akışlar dahil) ve simgesinde kaç tane olduğunu yazar. Seç, kaliteyi ve altyazıyı belirle, **MP4** ya da **MP3** indir. Oynatıcının başlıkları da gider; yalnızca kendi oynatıcısına cevap veren siteler bile iner. Kopya korumalı (DRM) yayınlar indirilemez.
- **📺 Dizi modu:** dizi sayfasında eklenti bölümleri bulur (Bölüm 1, S02E03 …). Seçtiklerin küçük, sessiz bir pencerede sırayla açılır, videoları yakalanır ve DISO'ya "Dizi - S01 Bölüm 02" adıyla, dizinin kendi klasörüne gönderilir.
- **DISO kapalıysa kendisi açılır:** eklenti onu başlatır (tarayıcının "native messaging" kanalıyla, IDM'in yaptığı gibi), hazır olmasını bekler ve linki verir.
- **Tarayıcının kendi indirmelerini yakalama** (isteğe bağlı): seçilen türdeki ya da belli boyutun üstündeki dosyalar DISO'ya gider. DISO açılamazsa tarayıcı normal şekilde devam eder.
- Araç çubuğundaki düğme **DISO'nun şu an ne indirdiğini** (sayı ve hız) gösterir; **▶ DISO'yu aç**, "bu sekmeyi indir" ve "bu sekmeyi MP3 olarak indir" düğmeleri vardır.
- Giriş isteyen sitelerde tarayıcının oturumu DISO'ya iletilir; çerezler diske yazılmaz. DISO yalnızca bu bilgisayarda dinler ve web sayfalarından değil, yalnızca eklentiden gelen istekleri kabul eder.

**Eklemek:** DISO açıldıktan sonra bir kez sorar ("DISO'yu tarayıcına ekleyelim mi?"), kurulum da sorar; aynı rehber her zaman Ayarlar → **🧩 Tarayıcıya ekle**'de. Tarayıcılar kendi mağazaları dışından eklentiyi kendiliğinden kurmadığı için üç tık sürer: rehber eklentiler sayfasını ve eklenti klasörünü açar, klasörün yolunu panoya kopyalar; **Geliştirici modu**nu aç, **Paketlenmemiş öğe yükle**'ye bas, yolu yapıştır (`Ctrl+V`) ve **Klasör seç**'e bas. Klasör `C:\Program Files\ISO\DISO\browser_extension`; DISO güncellenince eklenti de orada güncellenir. Eklenti sürüm sayfasında `DISO-browser-extension-<sürüm>.zip` olarak da var.

**Firefox:** rehberi kullan (eklentinin Firefox kopyasını hazırlar), sonra `about:debugging` → "Bu Firefox" → **Geçici eklenti yükle** → onun `manifest.json`'u. Firefox yalnızca imzalı eklentileri kalıcı tuttuğu için Firefox kapanınca eklenti de kalkar.

## ⚙ Ayarlar

- **İndirme:** aynı anda kaç indirme (1–8), toplam **hız sınırı**, otomatik deneme sayısı, **proxy** (http / socks5, **Dene** düğmesiyle), zamanlayıcı ve **tüm indirmeler bitince** ne yapılacağı (DISO'yu kapat / uyut / bilgisayarı kapat).
- **Sistem:** kapatınca arka planda çalış (sistem tepsisi), Windows ile başlat, bildirimler, günlük dosyası.
- **Görünüm:** tema (koyu / açık / sistem), **vurgu rengi** (pembe, mavi, yeşil, turuncu, mor, kırmızı) ve stil: **Standart (Önerilen)** (yeni bir bilgisayarın ilk görünümü: Yeni'nin renkleri, Nostalji'nin renkli resimleri), **Yeni**, **Klasik** ya da **🕹 Nostalji** (menü çubuğu, büyük resimli araç çubuğu, solda kategoriler ve tablo; 2000'lerin indirme yöneticileri gibi, açık ya da koyu gri). Değişiklikten sonra DISO aynı yerde yeniden açılır.
- **👤 Hesap:** hesap aç (ad, kullanıcı adı, 6 haneli kodla doğrulanan Gmail) ya da giriş yap, isteğe bağlı; adın sağ üstte yazar. Ayarlar, çalma listeleri, kanallar ve geçmiş bilgisayarların arasında eşitlenir; yeni bir bilgisayarda listelerin şarkıları tek tıkla iner. **💻 Bağlı bilgisayarlar** hepsini gösterir, istediğinden çıkış yaptırır; **🗑 Hesabı sil** hesabı kalıcı olarak siler.
- **👥 Arkadaşlar, sohbet ve gruplar:** kullanıcı adıyla arkadaş ekle (e-postalar hiç görünmez), onlarla ve gruplarda (yönetici, anma) yazış, şarkı öner, ➕ ile şarkı, çalma listesi, resim ve dosya gönder, yanıtla, tepki ver, beğendiklerini (👍 / 👎) ve şu an dinlediklerini gör; hepsi bir saniye içinde bildirim olarak gelir.
- **👋 Turlar:** indirme penceresi (ilk açılış) ve müzik çalar (ilk açıldığında) için adım adım tur, bazı adımları kendin denersin; Ayarlar → Yedek ve yardım'dan yeniden açılır.
- **💾 Yedek ve yardım:** ayarları, çalma listelerini, indirme listesini, geçmişi ve kanalları tek bir `.disoyedek` dosyasına yedekle, başka bir bilgisayarda geri yükle; **📊 İndirme geçmişi**; **⌨ Klavye kısayolları** (her yerde **F1**); sağlık kontrolü ve sorun bildirme.
- **ℹ Hakkında** (ya da başlıktaki sürüm rozetine tıkla): sürüm, DISO'nun ve verilerinin nerede olduğu. **📋 Detayları kopyala** DISO, Windows, yt-dlp, FFmpeg ve Deno sürümlerini panoya alır.

Seçtiğin her şey hatırlanır.

## 🌐 Dil
DISO, kurulumu ve tarayıcı eklentisi **Türkçe ve İngilizce** konuşur. İlk açılışta Windows Türkçe ise DISO Türkçe, değilse İngilizce başlar. İstediğin zaman sol üstteki **TR | EN** ile ya da Ayarlar → **Dil** ile değiştir (DISO yeniden açılır). Kurulum ve kaldırma pencerelerinde de **Türkçe | English** seçici var; tarayıcı eklentisi tarayıcının dilini kullanır.

## 🆕 Yenilikler
En yeni sürüm her zaman [sürümler sayfasında](https://github.com/muslimekc2112/DISO/releases/latest); bütün değişiklikler [`CHANGELOG.tr.md`](CHANGELOG.tr.md) dosyasında. 1.7'nin öne çıkanları:
- Hesabın yeni altyapısı **🏗 Supabase** (eski Firebase hesapları yeniden açılır), bağlantı yerine **🔐 6 haneli kodlar**.
- Yöneticili **👥 gruplar**, **➕ ekler** (şarkı, çalma listesi, resim, dosya), yanıtlama, tepkiler, okundu bilgisi ve **bir saniye içinde** gelen mesajlar.

Ve 1.6'nın:
- **👥 Arkadaşlar:** kullanıcı adıyla arkadaş ekle, **💬 yazış**, **🎵 şarkı öner**, **👍 / 👎** ve arkadaşlarının beğendiğini, şu an dinlediğini gör; hepsi **🔔 bildirim** olarak gelir.
- **🗑 Hesabı sil** (kalıcı olarak).

1.5'in öne çıkanları:
- **🎨 Standart (Önerilen):** yeni ilk görünüm, modern ve düğmelerde renkli resimler; kendi **vurgu rengin**.
- **👤 DISO hesabı tamamlandı:** hesap aç (ad, benzersiz kullanıcı adı, bağlantıyla doğrulanan Gmail) ya da giriş yap; adın sağ üstte; **💻 bağlı bilgisayarlar**; yeni bir bilgisayarda veriler ve listelerin şarkıları gelir.
- Kodla **🔗 listeyi arkadaşına gönder** ve **🎤 karaoke**.
- İndirme penceresi ve müzik çalar için **👋 turlar**, kendin denediğin adımlarla.
- **⚡ Ayarlar** anında açılıyor, akıcı genişliyor.

1.4 DISO hesabını getirdi (ayarlar, listeler, kanallar ve geçmiş eşitlenir). Ondan önce 1.3 serisinde: **〰 dalga ilerleme çubuğu**, **⏭ şarkılar arasında boşluksuz geçiş**, **😴 yavaşça kısılan uyku zamanlayıcısı**, eklentide **📺 dizi modu**, **🎨 müziğin rengi**, **✨ yumuşak geçişler** ve **⚡ daha hızlı** açılış.

## 🛠 Sorun giderme ve sorular
- **Windows "bilinmeyen yayıncı" diyor.** Paket dijital olarak imzalı değil. **Daha fazla bilgi → Yine de çalıştır**'a bas.
- **YouTube / Instagram birden çalışmaz oldu.** `⟳ Güncellemeler` → **Kontrol et**, sonra DISO'yu yeniden aç. DISO her açılışta yt-dlp, yt-dlp-ejs, FFmpeg ve Deno'ya bakar, yenisi varsa kendisi indirir (SHA-256 ile doğrulanır); yeni yt-dlp çalışmazsa kendiliğinden öncekine döner.
- **YouTube "format bulunamadı" diyor.** Kurulum paketindeki Deno yeterli. Kaynak koddan çalıştırıyorsan bir kez `winget install DenoLand.Deno` kur.
- **Video giriş istiyor.** **Giriş çerezleri** menüsünden giriş yaptığın tarayıcıyı seç (Firefox en sorunsuzu) ya da tarayıcı eklentisini kullan.
- **Google Drive / Mega / MediaFire sayfaları** doğrudan indirme linki değildir; DISO bir sayfadaki düğmeye basamaz.
- **FFmpeg kurmam gerekir mi?** Hayır. Kurulum paketinde var; kaynak koddan çalıştırırken ilk gerektiğinde DISO kendisi indirir (~115 MB, SHA-256 ile doğrulanır).
- **Ayarlarım ve listelerim nerede?** `%LOCALAPPDATA%\DISO` klasöründe. Diske güvenle yazılır ve son sağlam bir kopyası (`.bak`) tutulur; elektrik kesilse bile listelerin boşalmaz.
- **Başka bir sorun mu?** Ayarlar → **🩺 Sağlık kontrolü** çoğu sorunu bulur, birçoğunu tek tıkla düzeltir.

## 🔨 Geliştirenler için

<details>
<summary><b>Kaynak koddan çalıştırma, derleme, testler</b></summary>

### Çalıştırma ve derleme
1. Python 3.10+ kur (**"Add Python to PATH"** işaretli olsun).
2. `run.bat` dosyasına çift tıkla: kütüphaneleri kurar ve DISO'yu açar. Elle: `pip install -r requirements.txt`, sonra `python main.py`.
3. `build.bat` kurulum gerektirmeyen, tek dosyalık taşınabilir bir `DISO.exe` yapar (daha küçüğü için `build.bat --no-ffmpeg`). Her açılışta kendini açtığı için birkaç saniye geç açılır.
4. `python tools/build_installer.py` kurulum paketini yapar: DISO'yu klasör halinde derler (`build\app\DISO`), Deno'yu indirip SHA-256 ile doğrular ve `dist\DISO-Setup-<sürüm>.exe` çıkarır. Kurulan DISO 2–3 saniyede açılır.
5. İkonlar tek bir resimden üretilir: `IKON\icon.png` değişince `python tools/make_icons.py`.

İsim, yayıncı, sürüm ve GitHub adresi tek yerde: `app/brand.py`. Arayüz metinleri Türkçe yazılır; İngilizceleri `app/lang_en.py`'de (anahtarlar ekrandaki Türkçe metinler).

### Testler
`run_tests.bat` (ya da `python -m pytest`) bütün testleri internet gerekmeden çalıştırır: testler yerel bir sunucuyla Range desteği olmayan, bağlantısı kopan ya da bağlantı sınırlayan sunucuları, bir proxy'yi ve PyPI'yi taklit eder. Eklentinin mantığı `node` ile sınanır. İngilizce arayüz ve kurulum gerçekten açılır, ekranda Türkçe yazı kalmadığı denetlenir. FFmpeg, ekran, node ya da aria2 gerektiren testler bunlar yoksa atlanır. Kurulum testleri (`-m installer`) gerçek `DISO-Setup`'ı geçici bir yerde çalıştırır, Başlat menüne ya da kayıt defterine asla dokunmaz.
- Sadece hızlı testler: `python -m pytest -m "not gui and not ffmpeg and not exe and not installer"`
- Tek dosya: `python -m pytest tests/test_downloader.py`
- Ekranına pencere çıkmadan: `python tools/run_hidden.py -- python -m pytest tests` (testler kendi masaüstlerinde çalışır; görev çubuğu isteyen birkaç test orada atlanır)
- Kurulumu pencere açmadan denetle: `python main.py --selftest sonuc.json`

DISO'nun içinin nasıl çalıştığı, ayrıntısıyla: `NASIL_YAPILDI.txt` (İngilizcesi `HOW_IT_WAS_MADE.txt`).

</details>

## ✉ Bize ulaş
Bir hata mı buldun, bir fikrin mi var? [GitHub'da yeni bir sorun aç](https://github.com/muslimekc2112/DISO/issues/new); Türkçe ya da İngilizce yazabilirsin. Hata bildiriyorsan önce DISO'da Ayarlar → **ℹ Hakkında** → **📋 Detayları kopyala**'ya bas ve metni sorunun içine yapıştır (**✉ Bize ulaş** düğmesi aynı sayfayı açar). Günlük dosyası da işe yarar: `%LOCALAPPDATA%\DISO\diso.log`.

## 📄 Lisans
MIT: bkz. [`LICENSE`](LICENSE). Sürüm geçmişi: [`CHANGELOG.tr.md`](CHANGELOG.tr.md).
