# Sürüm geçmişi

## 0.10.0 beta
Program **DISO** adını aldı (yayıncı: ISO) ve ilk beta sürümü oldu. Numara 1.1.0'dan 0.10.0'a indi: "hazır" demek için erken, beta demek doğru.

**Yeni**
- Yeni ad, yeni ikon, ikona uyan mor palet; başlıkta BETA rozeti.
- **Hakkında penceresi** (Ayarlar'da ya da BETA rozetine tıkla): sürüm, klasörler ve bir tıkla panoya "detayları kopyala".
- Sürüm hatırlanır: ilk açılışta hoş geldin, güncellemeden sonra "… sürümüne güncellendi" der.
- **Kurulum paketi** (`DISO-Kurulum-<sürüm>.exe`): Python gerektirmez, `C:\Program Files\ISO\DISO` klasörüne herkes için kurar, Deno'yu getirir, kaldırıcısı vardır. Eski "Hızlı İndirici" kurulumunu kaldırır ve verilerini taşır.
- Müzik çalar: tablo (sıra, parça, sanatçı, süre), kapak resmi, toplam süre; biten müzik indirmeleri çalma listesine kendiliğinden girer; indirmenin sağ tık menüsünden listeye eklenir.
- **🔍 Şarkı bul:** müzik çalardan YouTube'da şarkı ara, MP3 olarak arka planda indir (yalnızca yüzde görünür), bitince "hangi listeye?" sorusuyla listene koy. Şarkılar `%LOCALAPPDATA%\DISO\Müzik` klasörüne iner.
- Müzik çalar: silinen dosyalar listeden kendiliğinden çıkar, listede arama, sütuna tıklayıp sıralama, sağ tık menüsü (klasörde göster, başka listeye ekle), kaldığın yerden devam, uyku zamanlayıcısı, klavye medya tuşları.
- **🎤 Şarkı sözleri** (LRCLIB): bulunan şarkılarla kendiliğinden gelir, şarkıyla akan söz penceresi, satıra tıklayınca oraya atlama; sözü olan şarkıda oynatıcıda 🎤 düğmesi.
- **🔀 Listeyi karıştır** (Ctrl+Z ile geri alınır).
- "Sanatçı - Şarkı" biçimindeki YouTube başlıkları sanatçı ve şarkı olarak ayrılır (kanal adı sanatçı sanılmaz).
- Arayüz metinleri daha samimi, kurucu da artık "sen" diliyle konuşuyor.

- **Müzik çalar:** sıradaki olarak çal / sıraya ekle, şarkılar arası geçiş (crossfade), mini oynatıcı, görev çubuğu önizlemesinde ⏮ ⏯ ⏭, Windows ses panelinde şarkı ve kapak.
- **Şarkı bul:** 30 saniyelik önizleme, YouTube önerileri ve arama geçmişi, YouTube Music listesi/albümü linkinden "Hepsini indir" (listenin adıyla, sırasıyla).
- **📊 İndirme geçmişi ve istatistik**, **💾 yedek al / yedeği yükle**, **⌨ klavye kısayolları (F1)**, **İngilizce arayüz** (Ayarlar → Dil).

**Değişti**
- Veriler `%LOCALAPPDATA%\DISO` klasöründe (eskiden kullanıcı klasöründe `.hizli_indirici`). İlk açılışta kendiliğinden taşınır.
- Kurulum tüm kullanıcılar içindir ve yönetici izni ister (eskiden kullanıcıya özel, izinsizdi).
- Tarayıcı eklentisi de 0.10.0; Firefox eklenti kimliği `diso@iso.local`.

**Düzeltildi**
- **Müzik çalar bazı şarkıları çalamıyordu**: kapak resmi büyük MP3'ler (~128 KB üstü, Windows açamıyor) ve sesi Opus olan videolar (VP9/AV1 MP4). Artık bunların çalınabilir kopyası arka planda hazırlanır (`%LOCALAPPDATA%\DISO\play_cache`, en fazla 1 GB; dosyanın kendisine dokunulmaz), bu sırada "⏳ Çalmaya hazırlanıyor…" yazar, sonra tıkladığın şarkı çalar. Eskiden sessizce sıradakine geçiyordu.
- Yeni MP3 indirmelerinde kapak en fazla 600 px / 90 KB gömülür, bu sorun baştan çıkmaz.
- Yazıların titremesi (değişmeyen şeyler artık yeniden çizilmiyor).
- Tema değişince ayarlar penceresinin kaybolması.
- Kapak resmi olan parçadan olmayana geçerken çıkan hata ve müzik penceresinin saatinin durması.
- **Altyazılı indirme:** YouTube altyazıyı reddedince (çeviri altyazılarında sık olur, "429 Too Many Requests") yedek indirme yolu videonun tamamını başarısız sayıyordu; hızlı yolda da altyazı sessizce gelmiyordu. Artık altyazı videoyu asla bozmaz, bir kez daha denenir, olmazsa videonun kendi dilindeki altyazı kaydedilir ve altyazı MP4'ün içine de gömülür.
- **Açılış hızlandı:** kurulum artık DISO'yu klasör halinde koyuyor (DISO.exe + `_internal`). Eskiden tek büyük exe her açılışta ~115 MB'ı geçici klasöre açıyordu (6–7 sn); şimdi 2–3 sn. Tek dosyalık exe kurulumsuz taşınabilir sürüm olarak duruyor. Kurucu iç içe klasörleri de tek tek kaydediyor: kaldırınca ya da yarıda kalan kurulum geri alınınca boş klasör kalmıyor; tek dosyalık eski kurulumun üstüne kurmak da sorunsuz.
- **Kapanış hızlandı:** pencereler Kapat'a basınca anında kaybolur; müzik listesi etiket okurken kapanış 3 sn bekliyordu (artık ~0,3 sn); bilgisi alınan indirme kapanışı bekletmez, kayıt için en fazla 6 sn beklenir (eskiden 15).
- **İndirme daha çabuk başlar:** açılıştaki yt-dlp/FFmpeg güncelleme kontrolü bitene kadar (90 sn'ye kadar) hiçbir video indirmesi başlamıyordu; artık beklemez, yt-dlp açılışta arka planda hazırlanır. YouTube, Instagram, TikTok gibi bilinen sitelerde "dosya mı video mu" sorusu atlanır; takılan istek 30 yerine 15 sn'de yeniden denenir.
- Müzik çalar, şarkı sözleri, Ayarlar, Hakkında ve diğer bütün pencerelerin başlık çubuğunda customtkinter'ın mavi ikonu yerine DISO logosu; müzik çaların başlığında da gerçek logo.
- **Yanlış şarkı sözleri:** LRCLIB aynı adlı başka bir şarkının sözlerini getirebiliyordu (yalnızca şarkı adına bakılıyordu). Artık sözler önce YouTube Music'ten, inen videonun kendisinden geliyor; LRCLIB'in zamanlaması yalnızca metin aynıysa kullanılıyor, LRCLIB tek başına kalırsa sanatçı da tutmalı. Yanlış kalmış eski sözler için "yeniden bul".
- Kaldırıcı boş kalan `C:\Program Files\ISO` klasörünü de siler.
- Kurucu/kaldırıcıda: yükseltmede ortada hata olursa dosyaların eksik kalması, kaldırıcının kendi sürecini kapatması, pencerede kilitlenme.
