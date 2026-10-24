# Sürüm geçmişi

**[English](CHANGELOG.md) | Türkçe**

## 1.5
- **🎨 Yeni görünüm: Standart (Önerilen).** DISO ilk kez açıldığında bu görünümle gelir. "Yeni"nin modern renkleri ve yuvarlak düzeni, "Nostalji"nin renkli, parlak simgeleriyle birleşti: düğmelerdeki tek renkli emojiler yerine renkli resimler (pano, dosya, mıknatıs, telefon, ayarlar, ekolayzır, hesap…). Düğmeler sakin, ana "⬇ İndir" vurgu renginde. Eski görünümler Ayarlar → Görünüm stili'nde duruyor; var olan kullanıcıların seçimi değişmez.
- **👋 Yeni eğitim turları:** indirme penceresi için 13 adımlık tur ilk açılışta, müzik çalar için 12 adımlık tur müzik çalar ilk açıldığında gelir; ikisi hiç aynı anda açılmaz. Tur penceresi anlattığı yerin hemen yanına gelir ve orayı çerçeveler. Ayarlar → Yedek ve yardım → "Turu yeniden göster" ve müzik çaların ⚙ menüsünden yeniden açılır.
- **🎨 Vurgu rengi:** Ayarlar → Görünüm'de pembe, mavi, yeşil, turuncu, mor ya da kırmızı. Bütün pencerenin tonu seçilen renge uyar; yazılar her renkte okunaklı kalır (kontrast kendiliğinden ayarlanır).
- **👉 Uygulamalı tur:** turun bazı adımlarında "Dene" çıkar (link yapıştır, İndir'e bas, Şarkı bul'a geç); yapınca "✔ Harika!" der ve kendisi ilerler.
- **💻 Bağlı bilgisayarlar:** hesap penceresinde hesabına giriş yapmış bütün bilgisayarlar (adı, son görülme, sürüm); istediğinden "Çıkış yaptır" (o bilgisayar bir sonraki açılışında ya da birkaç dakika içinde hesabı unutur).
- **🔗 Listeyi arkadaşına gönder:** müzik çaların ⚙ menüsünden; şarkıların linkleri bulunur, sana bir kod (ör. K7P2-QM4X) ve link verilir. Arkadaşın "📥 Paylaşılan listeyi aç"a kodu yazınca ya da linke tıklayınca liste onda oluşur ve şarkılar MP3 olarak iner (almak için hesap gerekmez).
- **🎤 Karaoke:** müzik çaların ⚙ menüsünden; şarkıcının sesi kısılır (bas korunur), sözler görselleştiricide şarkıyla akar. Kulaklık ya da iki hoparlörle en iyisi.
- **⚡ Ayarlar hızlandı:** açılması ~0,9 sn'den ~0,07 sn'ye indi (arka planda önceden hazırlanır); kenarından genişletirken kasma bitti (her adım 165 ms'den ~23 ms'ye).
- **👤 Nostalji'de de hesap:** araç çubuğunun sağ ucunda adın (ya da "Giriş yap").
- **👤 Hesap aç ve Giriş yap ayrı ekranlar:** hesap açarken ad, soyad, kullanıcı adı (benzersiz), Gmail ve iki kez şifre istenir. Gmail'e bir doğrulama bağlantısı gider; hesap ancak bağlantıya tıklayıp "Doğruladım" deyince açılır ("Gmail'i aç", "Tekrar gönder", "Vazgeç" düğmeleri var).
- **Sağ üstte hesap:** indirme penceresinde ve müzik çalarda sağ üstte adın yazar; giriş yapılmamışsa "👤 Giriş yap", doğrulama bekleniyorsa "👤 Doğrula". Hesap penceresinde baş harflerinle bir yuvarlak, ad, @kullanıcı adı, e-posta, son eşitleme, "Şifreyi değiştir" ve "Çıkış yap".
- **Her açılışta "Bir DISO hesabı aç?"** sorusu (hesap yokken), "Bir daha gösterme"ye basana kadar.
- **Başka bilgisayarda ilk giriş:** "Verileri bu bilgisayara aktar" ya da "Buradakileri hesaba yükle" seçilir, ayrıca "Listelerdeki şarkıları da indir". Şarkılar indirme geçmişindeki linkinden (yoksa YouTube Music'te sanatçı + adla bulunarak) MP3 olarak iner ve listede eski yerine oturur. Hesap penceresinde "⬇ Listelerdeki eksik şarkıları indir" her zaman var.
- **Düzeltildi:** başka bilgisayardan gelen listelerin şarkıları, dosyaları henüz orada olmadığı için "silinmiş" sayılıp listeden atılabiliyor, bu da hesaba geri yüklenip ilk bilgisayardaki listeleri boşaltabiliyordu. Artık DISO'nun müzik klasöründeki şarkılar her bilgisayarda kendi müzik klasörünü gösterir; burada olmayanlar beklemeye alınır, atılmaz.
- **Düzeltildi:** Firebase'de e-postayla giriş kapalıyken anlaşılmaz "OPERATION_NOT_ALLOWED" yerine ne yapılacağı yazar.

## 1.4
- **👤 DISO hesabı:** Ayarlar → Hesap'tan e-posta ve şifreyle hesap açılır ya da giriş yapılır (isteğe bağlı). Ayarların, çalma listelerin, takip ettiğin kanallar ve indirme geçmişin her bilgisayarda aynı kalır. DISO açılırken başka bilgisayarda değişenler gelir; kapanırken ve 10 dakikada bir buradakiler hesaba gider. Bu bilgisayara özel ayarlar (klasörler, USB, bağlantı noktası, Windows'la başlatma) taşınmaz, şarkılar ve videolar da taşınmaz. İki bilgisayarda aynı dosya değiştiyse hesaptaki kazanır, buradaki `.before-sync` olarak saklanır. İlk girişte iki tarafta da farklı veri varsa hangisinin kalacağı sorulur. "Şifremi unuttum" e-postayla yeni şifre bağlantısı gönderir.
- **💾 Yedek** artık takip edilen kanalları da içerir.

## 1.3.1
- **Düzeltildi:** görselleştiricinin tam ekranı, ekran ölçeklemesi %100'den büyükken ekranın yalnız bir kısmını kaplıyordu; artık bütün monitörü kaplar ve çıkınca pencere eski boyutuna döner.
- **Düzeltildi:** Ayarlar açılırken yarım saniye titriyordu; artık tüm bölümleri hazır olunca tek seferde yumuşakça belirir.

## 1.3
- **↑ / ↓ ile ses:** müzik çalarda ↑ sesi açar, ↓ kısar (5'er); basılı tutunca önce yavaş, sonra gittikçe hızlı.
- **← / → yalnızca sarar:** iki kez basınca sonraki / önceki şarkıya geçme kaldırıldı; her basış 5 saniye, basılı tutunca sarmaya devam eder.
- **🎨 Müziğin rengi:** renk artık bütün pencerede değil, şarkının olduğu blokta ve müziğin o anına göre değişiyor (YouTube'daki ışık gibi): kapağın renkleri bas, orta ve tize göre karışır, ses yükseldikçe parlar. Duraklatınca sakin, kapağın kendi renginde kalır.
- **〰 Dalga çubuğu:** müzik çaların ilerleme çubuğu artık şarkının ses dalgası: yüksek yerler uzun, sessiz yerler kısa çubuk. Çalınan kısım vurgu renginde; üzerine gelince o saniye yazar, tıkla ya da sürükle, oraya atlar.
- **⏭ Boşluksuz geçiş:** şarkının son saniyelerinde sonraki şarkı ikinci çalarda açılıp hazır bekler (ekolayzır / hız açıkken çözülmeye de başlar) ve bu şarkı biterken tam o anda başlar; şarkılar arasında sessizlik kalmaz.
- **😴 Uykuda yavaşça kısılır:** uyku zamanlayıcısı müziği birden kesmez; son dakikalarda (15 dakikada son 2 dakika) ses yumuşakça sıfıra iner, sonra durur ve ses ayarın eski haline döner. "Parça bitince" seçiliyse şarkının son 10 saniyesi kısılarak biter.
- **📺 Dizi modu:** eklenti bir dizi sayfasındaki bölüm linklerini bulur (Bölüm 1, 2. Bölüm, S02E03, 3-sezon-12-bolum …). Seçtiğin bölümleri küçük, sessiz bir pencerede sırayla açar, oynatıcıyı başlatır, videoyu yakalar ve DISO'ya "Dizi Adı - S03 Bölüm 01" adıyla, dizinin kendi klasörüne gönderir. Videosu çıkmayan bölümün sayfası gönderilir (DISO kendisi dener). Sayfada sağ tık → "📺 Bu dizinin bölümlerini DISO ile indir" de var; ilerleme ve Durdur eklenti penceresinde.
- **🎞 Adı gizlenmiş akışlar:** bazı siteler video listesini `.txt`, `.png` gibi adlarla veriyor; eklenti artık bunları da içeriğinden (`#EXTM3U`) tanır.
- **✨ Yumuşak geçişler:** pencereler kararıp belirerek açılır ve kapanır; İndirme ↔ Müzik çalar geçişi yeni pencere eskisinin üstünde belirerek olur (boşluk, zıplama yok); şarkı değişince kapak bir sonrakine yumuşakça döner; tepsiden dönen pencere belirerek gelir.
- **⚡ Daha hızlı:** Ayarlar anında açılır (723 → ~140 ms; gruplar pencere açıkken arka arkaya gelir), müzik çalar penceresi açılıştan birkaç saniye sonra arka planda hazırlanır, böylece ilk geçiş de bekletmez.
- **Düzeltildi:** ekolayzırda "Gelişmiş"i açıp kapattıkça pencere sağa doğru uzuyordu (ekran ölçeklemesi %100'den büyükken).

## 1.2
- **🎞 Her siteden video ve MP3:** tarayıcı eklentisi sayfada oynayan videoları kendisi bulur (sayfanın içindeki gizli oynatıcılardakiler de: HLS `.m3u8`, DASH `.mpd`, düz video ve ses dosyaları) ve araç çubuğundaki simgesinde kaç tane bulduğunu yazar. Simgeye tıkla: **🎞 Bu sayfada bulunan videolar** listesinden istediklerini seç, **kaliteyi** (En iyi, 2160p … 360p) belirle, oynatıcının yüklediği **altyazıları da indir**, **🎬 MP4** ya da **🎵 MP3** olarak gönder. Oynatıcının gönderdiği başlıklar (Referer, Origin, çerezler) indirmeye eşlik eder; yalnız kendi oynatıcısına cevap veren sunucular da böylece iner. Dosya adı sayfanın başlığı olur ("index.m3u8" değil). Sayfada sağ tık → **🎞 Bu sayfada bulunan videoları DISO ile indir** de var. Kopya korumalı (DRM) yayınlar indirilemez.
- **Site desteklenmese de iner:** "🎬 MP4 olarak indir" ya da sağ tık → MP4/MP3 ile gönderilen bir sayfayı DISO önce kendisi dener; olmazsa sayfanın oynattığı videoya geçer ("Sayfa doğrudan inmedi; sayfada oynayan videoyu indiriyorum…").
- **Yarıda kalan akışa devam:** duraklatılan (ya da DISO kapanınca yarım kalan) HLS/DASH indirmesi indirdiği parçaları saklar ve kaldığı yerden sürer. İptal edilince yarım parçalar silinir.
- **🌌 Yeni görselleştirici:** yeni simge, kapağın renklerinden otomatik palet (**🎨 Kapaktan**, yeni varsayılan), arkada şarkıyla parlayan yumuşak bir ışık; **Halka**'nın ortasında şarkının kapağı yuvarlak durur ve her vuruşta hafifçe büyür, halka yavaşça döner; yuvarlak uçlu çubuklar. Altta **⏮ ⏪5 ⏯ 5⏩ ⏭** ve şarkının nerede olduğu; tam ekranda fare oynayınca görünür.
- **⏩ Çalma hızı ve perde:** 0.25x'ten 4x'e kadar (0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4) ve ±6 yarım ses perde; ses bozulmadan, şarkı kaldığı yerden sürer. Hız düğmesi oynatıcıda, ⚙ menüsünde de var; seçilen hız hatırlanır.
- **⏪5 / 5⏩ ve ← / →:** düğmeler 5 saniye geri / ileri sarar. Klavyede **→ bir kez: 5 sn ileri, iki kez art arda: sonraki şarkı**; **← bir kez: 5 sn geri, iki kez: önceki şarkı**. Basılı tutunca 5'er saniye sarmaya devam eder. (Eski Shift + ←/→ yerine; ⌨ Kısayolları ayarla'dan değiştirilebilir.)
- **⇅ Listeyi sırala:** listenin yanındaki menüden **Kendi sıram, Son eklenen en başta, Son eklenen en sonda, A → Z, Z → A** (Türk alfabesiyle: Ç, Ğ, İ, Ö, Ş, Ü yerinde) ya da **En popüler en başta**. Kendi sıran hep saklıdır, "Kendi sıram" onu geri getirir; sıralı bir listeye eklenen şarkı yerine girer, elle taşıyınca o sıra senin sıran olur.
- **🎨 Arka plan şarkının renginde:** müzik çaların arka planı çalan şarkının kapağının rengini YouTube'daki gibi hafifçe alır ve şarkı değişince yumuşakça geçer (⚙ menüsünden kapatılabilir).
- **🛡 Her indirmede Windows Defender:** biten her indirme (torrent klasörleri dahil) taranır, sonuç indirmenin altında yazar ("🛡 Windows Defender: temiz" / "⚠ tehdit buldu ve karantinaya aldı"); Defender kapalıysa (başka bir antivirüs) bunu da söyler.
- **🔔 Bildirimler DISO'dan:** bildirimler artık "Windows PowerShell" adıyla değil, DISO'nun adı ve simgesiyle gelir.
- **Düzeltildi:** kanal takibi bir kanalın sayfasını okurken sekmelerini ("Videos", "Shorts") video sanmasın diye ek koruma; "Neden inmedi?" desteklenmeyen sitelerde eklentinin 🎞 listesini gösteriyor.

## 1.1
- **🕹 Nostalji görünümü:** Ayarlar → Sistem → Görünüm stili → **Nostalji** (ya da menüden Görünüm → Görünüm stili). 2000'lerin gri Windows'u ve o zamanın indirme yöneticileri gibi bir pencere: menü çubuğu (Görevler, İndirmeler, Görünüm, Araçlar, Yardım), büyük resimli araç çubuğu (Yeni indirme, Devam et, Durdur, Hepsini durdur, Sil, Bitenleri sil, Ayarlar, Zamanlayıcı …), solda kategoriler (Video, Müzik, Sıkıştırılmış, Belgeler, Programlar, Bitmemiş, Bitmiş, Hatalı), indirmeler tablo halinde (Dosya adı, Boyut, Durum, Kalan süre, Hız …; başlığa tıkla, sıralansın), altta durum çubuğu. İnen bir indirmeye çift tıkla: yeşil bloklu ilerleme penceresi açılır; bitmişse dosya açılır. Ayarlar sekmeli, müzik çaların da menü çubuğu var; her yer Tahoma yazılı, gri ve hep açık renkli.
- **🌙 Koyu Nostalji:** Nostalji görünümünde Ayarlar → Görünüm → **Koyu** (ya da menüden Görünüm → Renk): aynı 2000'ler penceresi koyu gride döner. Değişince DISO yeniden açılır.
- **🧲 Torrent:** magnet linkleri, `.torrent` linkleri ve `📄 Dosyadan…` ile seçilen `.torrent` dosyaları DISO'da diğer indirmeler gibi iner: hız, eş sayısı, kalan süre, duraklat / devam et / iptal (iptal yarım dosyaları da siler). İşi aria2 yapar; ilk torrentte bir kereliğine indirilir (~2.5 MB) ve SHA-256 ile doğrulanır. İnen torrent paylaşılmaya devam etmez (DISO bir indirici). Tarayıcı eklentisi de magnet linklerini DISO'ya gönderir ve `.torrent` indirmelerini yakalar.
- **🩺 Sağlık kontrolü** (Ayarlar → Yedek ve yardım, ya da Nostalji'de Yardım menüsü): internet, YouTube, YouTube Music, GitHub, yt-dlp'nin yaşı, FFmpeg, Deno, aria2, tarayıcı eklentisi, indirme klasörü (yazılabiliyor mu, boş yer), DISO'nun dosyaları ve proxy tek tek denenir; ✓ / ⚠ / ✗ ile gösterilir, düzeltilebilenin yanında düğmesi vardır (FFmpeg'i kur, Deno'yu kur, Güncelle, Eklentiyi ekle …).
- **🐞 Sorun bildir:** masaüstüne bir zip (sürümler, sağlık kontrolü, günlük dosyası, ayarlar) koyar ve GitHub'da sürümleri yazılmış yeni bir sorun sayfası açar. Günlükteki linkler yalnız site adıyla kalır; çalma listeleri, geçmiş, çerezler ve proxy şifresi zip'te olmaz.
- **Deno da kendini güncelliyor:** YouTube için gereken JavaScript motoru (Deno) artık yt-dlp ve FFmpeg gibi Güncellemeler'de; yeni bir ana sürümü çıkınca (2.9 → 2.10) kendiliğinden indirilir, SHA-256 ile doğrulanır, denenmeden kullanılmaz. Senin ayrıca kurduğun bir Deno'ya dokunulmaz.
- **Dosyalar elektrik kesintisine dayanıklı:** ayarlar, çalma listeleri, indirme listesi, geçmiş ve kanallar diske kesin yazılır ve saatte bir son sağlam kopyası (`.bak`) tutulur. Biri bozulursa açılışta o kopyadan geri gelir (bozuk olan `.bozuk` olarak saklanır) ve DISO bunu söyler; eskiden bozuk bir dosya boş liste demekti.
- **⏫ En üste al:** sırada bekleyen bir indirmeye sağ tık → sıradaki o olur.
- **🎧 Daha iyi önizleme:** şarkının YouTube'da en çok tekrar dinlenen yerinden (çoğu zaman nakarat) başlar, yavaşça girip yavaşça çıkar, `0:12 / 0:30` diye ne kadar kaldığını gösterir. Bir sonuç seçilince önizlemesi arka planda hazırlanmaya başlar, böylece "🎧 Önizle" çoğu zaman hemen çalar; bir kez dinlenen önizleme saklanır (son 30), yeniden anında çalar.
- **Daha hızlı açılış:** DISO her açılışta "başka bir DISO açık mı?" diye kendi kapısını yoklarken Windows 1,5 saniye bekliyordu; artık bu anında anlaşılıyor.
- **🧲 Torrentte dosya seçimi:** birden çok dosyalı bir torrent eklenince, daha hiçbir şey inmeden dosyaları bir pencerede gelir: klasör ağacı ve tik kutuları (klasöre tıklayınca içindekilerin hepsi), hızlı seçim (Hepsi, Hiçbiri, Videolar, Müzik, Resimler, Belgeler, Arşivler), dosya arama, seçilenin boyutu ve diskteki boş yer (yetmezse kırmızı uyarı). Yalnız seçilenler iner; seçim hatırlanır (duraklatıp ya da DISO'yu kapatıp açınca yeniden sorulmaz). İnerken sağ tık → **🧲 Dosyaları seç…** ile seçim değiştirilebilir. Hep hepsini indirmek için: pencerede "Bir daha sorma" ya da Ayarlar → İndirme.
- **✏ Dosya adlarını düzenle** (müzik çalarda şarkılara sağ tık, ya da Nostalji'de Liste menüsü): seçilen şarkıların (seçim yoksa listenin) dosya adları bir kalıptan: `{sanatçı} - {şarkı}`, `{no}. {şarkı}`, `{sanatçı} - {albüm} - {şarkı}` ya da kendi kalıbın. Önizlemede her yeni ad, aynı adlı dosya varsa uyarı; "Baş Harfleri Büyük", "Türkçe harfleri sadeleştir". Şarkının sözleri (.lrc) de birlikte taşınır, listeler yeni adları izler, çalan şarkı kesilmez; **↶ Geri al** ile eski adlar döner.
- **🖼 Kapağı internetten bul:** şarkıya sağ tık → "Kapağı internetten bul", ⚙ menüsü → "Kapağı olmayanlara kapak bul" (listenin hepsi) ya da şarkı bilgileri penceresinde **🌐 İnternetten bul**. Kapak YouTube Music'ten gelir (DISO'dan inen şarkıda kendi videosununki, yoksa aynı ad ve sanatçıdaki şarkınınki; başka şarkının kapağı gelmez), 544×544 olarak dosyanın içine yazılır.
- **📈 Hız grafiği:** indirme listesinin altında son bir dakikanın hızı; Nostalji'de durum çubuğunda o zamanların yeşil-siyah grafiği, ilerleme penceresinde de o indirmenin kendi grafiği (şu anki ve en yüksek hız).
- **Şarkı sözleri ve kapaklar:** "Gülpembe" ile "Gül Pembe" gibi yalnız boşluğu farklı adlar artık aynı şarkı sayılıyor.
- **🔧 Dosyayı kontrol et / onar** (biten indirmeye sağ tık): dosya yerinde mi, sunucudaki kadar büyük mü, içi okunuyor mu (zip / tar / gz arşivleri, PDF, resimler, videolar ve şarkılar FFmpeg ile) bakar. Yalnızca sonu eksikse **yalnız eksik kısmı** indirip dosyayı tamamlar; bozuksa silip baştan indirmeyi önerir.
- **📋 Panodaki linki sor:** "Panoyu izle" açıkken bir link kopyalayınca sağ alt köşede küçük bir pencere çıkar: **⬇ İndir**, **🎬 MP4**, **🎵 MP3** ya da **Hayır** (DISO tepsideyken de). Eski gibi sormadan eklemesi için: Ayarlar → İndirme → "Kopyalanan linki indirmeden önce sor".
- **🎵 FLAC, OGG, Opus** (ve AIFF, WavPack, APE, MKA) müzik çalarda doğrudan çalar: dönüştürülmüş kopya beklenmez, ses kaybı yok; listelere de eklenir, biten indirmelerde kendiliğinden listeye girer.
- **🔊 Ses seviyesini eşitle** (müzik çalarda ⚙ menüsü): her şarkının ses yüksekliği bir kez ölçülür (EBU R128, arka planda); çok yüksek kaydedilmiş şarkılar biraz kısık çalar, böylece şarkılar arası ses zıplamaz. Şarkılar arası geçişte de her şarkı kendi seviyesinde.
- **🏷 Şarkı bilgilerini düzenle** (müzik çalarda şarkıya sağ tık): adı, sanatçısı, albümü, yılı, türü ve **kapak resmi** dosyanın içine yazılır (MP3, M4A, FLAC, OGG, Opus, WAV, WMA; kapak MP3 / M4A / FLAC'ta). Ses dosyası yeniden kodlanmaz; çalan şarkı kaldığı saniyeden devam eder.
- **✎ Şarkı sözlerini elle yaz / yapıştır:** sözler penceresinde **✎ Düzenle** (ya da şarkıya sağ tık). `[01:23.45]` ile başlayan satırlar şarkıyla akmaya devam eder; boş bırakıp kaydedersen sözler silinir.
- **📤 / 📥 .m3u listeleri:** müzik çalarda ⚙ menüsü (Nostalji'de Liste menüsü): listeyi `.m3u8` olarak dışa aktar (telefona, başka çalara), ya da başka bir çaların `.m3u` / `.m3u8` / `.pls` listesini yeni bir liste olarak içe aktar.
- **Daha küçük kurulum paketi (214 → ~110 MB):** program kurulum dosyasının içinde çok daha sıkı (xz) sıkıştırılıyor ve ayrı bir kaldırıcı (Uninstall.exe, içinde ikinci bir Python) artık yok: DISO'yu kurulu DISO.exe'nin kendisi kaldırıyor (`DISO.exe --uninstall`; Uygulamalar listesi ve Başlat menüsündeki "DISO'yu Kaldır" bunu çağırır).
- **Şarkı sözleri:** YouTube Music bağlantıyı koparırsa DISO bir kez daha sorar (önce hemen "bakamadım" diyordu).
- **Tarayıcı eklentisi:** tarayıcının DISO devralmadan önce bitirdiği küçük bir dosya artık ikinci kez indirilmez.
- **Görünüm değişince her şey yerinde:** stil ya da dil değişip DISO yeniden açılınca pencere aynı yerde ve aynı boyutta açılır, müzik çalardaysan müzik çalar, Ayarlar açıksa Ayarlar (aynı sekmede) gelir; çalan şarkı kaldığı yerden devam eder.
- **Yalnızca Windows:** Linux sürümü bırakıldı (1.0'ın Linux paketleri olduğu gibi kalır, yenisi çıkmayacak).
- **🔄 DISO kendini güncelliyor:** yeni sürüm çıkınca haber verir; `⟳ Güncellemeler` → DISO → **Güncelle** dersen indirir, SHA-256 ile doğrular, kurar ve yeni sürümle açılır. Sen istemeden hiçbir şey indirmez; Windows'un izin sorusuna "hayır" dersen DISO çalışmaya devam eder.
- **📺 Kanal takibi:** takip ettiğin kanallara yeni video gelince bildirim; hiçbir şeyi kendiliğinden indirmez, seçtiklerini MP4 / MP3 indirirsin.
- **✂ Video kırpma:** ℹ penceresinde Başlangıç / Bitiş yaz, videonun yalnızca o kısmı iner.
- **🎛 Ekolayzır:** 8 bant ve hazır ayarlar; düzken ses hiç değişmez.
- **✨ Akıllı listeler:** ⭐ En çok dinlenenler, 🆕 Son eklenenler, 💤 Hiç dinlenmeyenler.
- **Düzeltildi:** en küçük pencere boyutunda "Panoyu izle" kesiliyordu; İngilizcede "Eklendi: MP3" gibi bildirimler çevrilmiyordu.
- **Düzeltildi (önemli):** "Tarayıcı indirmelerini yakala" açıkken, tarayıcı açıldığında eklenti tarayıcının **eski indirmelerinin hepsini** DISO'ya gönderip yeniden indirtiyor (ve tarayıcının indirme geçmişinden siliyordu). Tarayıcı açılırken geçmişteki indirmeleri de "yeni" diye bildiriyor; eklenti artık yalnızca o anda başlayan indirmeleri yakalıyor, bitmiş, yarıda kalmış ya da eski indirmelere hiç dokunmuyor. Eklentiyi güncellemek için: `chrome://extensions` → DISO → ↻ (yeniden yükle).
- **Şarkı bul yalnızca YouTube Music:** sonuçlarda artık yalnızca şarkılar var; YouTube videoları, "lyrics" videoları, klipler ve shorts gelmiyor (az sonuç olunca videolar eklenmiyor, YouTube Music'e ulaşılamazsa düz YouTube'da aranmıyor; bir kez daha deneyip "YouTube Music'e ulaşılamadı" diyor).
- **Şarkı sözleri yalnızca YouTube Music'ten:** LRCLIB bırakıldı (aynı adlı başka bir şarkının sözlerini getirebiliyordu). İnen videonun sözü yoksa YouTube Music'te aynı ad ve sanatçıdaki, uzunluğu en yakın şarkının sözleri alınıyor; Türkçe harf farkları ("Şımarık" / "Simarik") artık sorun değil. Yanlış kalmış eski sözler için sağ tık → "🔄 Sözler yanlış, yeniden bul".

## 1.0
- **DISO 1.0: beta bitti.** Aşağıdakilerin hepsi içinde; Windows'ta ve artık Linux'ta da.
- **Linux:** DISO artık Linux'ta da çalışıyor: Debian, Ubuntu, Mint … için `.deb` ve her dağıtım için `.tar.gz` (içindeki `install.sh` ile, yönetici şifresi gerekmeden). FFmpeg, yt-dlp ve Deno içinde gelir; DISO onları orada da kendisi günceller (FFmpeg: BtbN derlemeleri, SHA-256 ile doğrulanır).
- **Kurulum ve kaldırma iki dilli:** `install.sh` ve `uninstall.sh` Türkçe / English sorar; kaldırırken ayarlarının, çalma listelerinin ve geçmişin de silinip silinmeyeceğini sorar (indirdiğin dosyalara dokunmaz). Uygulamalar menüsünde "DISO'yu Kaldır" var.
- **Müzik çalar Linux'ta:** sesi FFmpeg çözüyor, SDL çalıyor; her dosya türü (Opus, Vorbis, FLAC …) dönüştürmeden çalar, geçiş (cross-fade) ve önizleme de var.
- **Tarayıcı eklentisi Linux'ta:** DISO kapalıyken eklenti onu açabilir (her tarayıcının kendi klasörüne küçük bir dosya yazılır). Eklenti rehberi tarayıcıları orada da bulur; **Chromium** da listede.
- **Oturum açılınca başlat** (autostart), bildirimler (notify-send) ve "bitince bilgisayarı kapat / uyut" Linux'ta da çalışıyor.
- Yalnızca Windows'ta kalanlar: medya tuşları, görev çubuğu önizleme düğmeleri ve Windows medya paneli.
- Taşınabilir `DISO.exe` artık sürümlere eklenmiyor (kurulumu kullan).

## 0.11.5 beta
- **Ana pencerenin sol üstünde TR | EN:** dili tek tıkla değiştir (DISO yeniden açılmayı önerir; Ayarlar → Dil ile aynı şey).
- **Düzeltildi:** Ayarlar'da (ve kaydırılan diğer pencerelerde) tekerlekle hızlı kaydırınca satırların kopyaları ekranda kalıyor, yazılar bozuk görünüyordu. Tekerlek adımları artık birleştirilip tek seferde kaydırılıyor ve hemen yeniden çiziliyor.
- **Düzeltildi:** bazı yazıların sonu kesiliyordu: Ayarlar'daki açıklamalar ("…kaldığı yerden devam ederim", "…kendi adıyla yeni bir listeye gider", "…hep açık kalır"), Ayarlar'ın altındaki sürüm yazısı ("SO 0.11.4 be"), ana penceredeki "Otomatik (dosya / video)" ve pencereler küçültülünce Güncellemeler, Kısayollar, Hakkında ve eklenti rehberindeki uzun metinler. Uzun metinler artık pencerenin genişliğinde alt satıra geçer; sürüm Ayarlar'ın sağ üstünde.

## 0.11.4 beta
- **Kurulum ve kaldırma pencerelerinde dil seçici:** sağ üstte **Türkçe | English**. Pencere DISO'nun diliyle (DISO hiç açılmadıysa Windows'un diliyle) açılır, istersen değiştirirsin; kurulum ya da kaldırma başlayınca dil sabitlenir. Kurulumda seçtiğin dil DISO'nun dili de olur (diğer ayarlarına dokunulmaz).
- **Kaldırma:** Başlat menüsünde DISO'ya sağ tık → Kaldır, Windows'un uygulama listesini açar; oradaki Kaldır, DISO'nun kaldırıcısını açar ve "Ayarlarımı ve çalma listelerimi de sil" seçeneğini sorar. Başlat menüsündeki "DISO'yu Kaldır" doğrudan kaldırıcıyı açar.
- **Düzeltildi:** İngilizceye pencere açıkken geçildiğinde, ondan önce oluşturulmuş seçim düğmeleri hata veriyordu.

## 0.11.3 beta
- **Şarkı bul artık YouTube Music'ten arar:** shorts ve sıradan videolar sonuçları doldurmaz, şarkılar gelir (50'ye kadar). Yazdığına uyanlar en üstte, en çok dinlenen önce; yeni **Dinlenme** sütunu her şarkının ne kadar dinlendiğini gösterir. Az şarkı bulunursa YouTube Music'in müzik videoları da eklenir. YouTube Music'e ulaşılamazsa YouTube'da aranır (shorts olmadan).
- **Sanatçı / kanal kutusu:** arama kutusunun yanına sanatçının ya da kanalın adını yaz, yalnızca onun şarkıları gelsin. Şarkı adıyla birlikte ya da tek başına (o sanatçının en popüler şarkıları) kullanılır; boş bırakılırsa aramayı etkilemez. Büyük-küçük harf ve Türkçe harfler fark etmez ("simarik" = "Şımarık").
- **Düzeltildi:** indirme türü MP4 ya da MP3 seçiliyken normal bir dosya (zip, rar, exe, pdf…) videoya/sese çevrilmeye çalışılıyordu. Artık DISO linkin ne olduğuna bakar ve dosyayı olduğu gibi indirir; video siteleri, sayfalar ve ses/video dosyaları seçime göre iner.
- **Tarayıcı eklentisi linkin ne olduğunu kendisi söyler:** dosya linkleri ve yakalanan tarayıcı indirmeleri DISO'ya "dosya" olarak gider (uygulamadaki MP3/MP4 seçimi onları değiştirmez), sayfa linklerine DISO bakar. Eklenti düğmesinde **🎬 MP4 olarak indir** ve **🎵 MP3 olarak indir** var ("Bu sekmeyi indir" kalktı); sayfanın sağ tık menüsünde de ikisi var.
- **Düzeltildi:** Güncellemeler'de FFmpeg, DISO ile geldiği hâlde "Kendi kurulumun" görünüyordu. DISO ile gelen FFmpeg artık DISO'nundur: yenisi çıkınca DISO onu kendisi günceller. "Ayrıca kurulu" yalnızca bilgisayarda ayrıca kurulmuş başka bir FFmpeg için görünür.

## 0.11.2 beta
- **Düzeltildi:** Chrome eklentiler sayfasında "'background.scripts' requires manifest version of 2 or lower" uyarısı gösteriyordu (zararsızdı ama hata gibi görünüyordu). Artık Chrome ve Firefox'un ayrı manifest dosyaları var: `manifest.json` yalnızca Chrome'un anladıklarını içerir, `manifest.firefox.json` Firefox'unkidir. Rehberdeki Firefox düğmesi Firefox kopyasını kendisi hazırlar; sürümde ayrıca bir Firefox zip'i de var.
- **Düzeltildi:** taşınabilir `DISO.exe` ile eklentinin klasörü (`%LOCALAPPDATA%\DISO\browser_extension`) yalnızca rehber açılınca güncelleniyordu; artık her açılışta. Böylece yeni DISO.exe eklentiyi de günceller (tarayıcıda eklentinin yenile düğmesine bas ya da tarayıcıyı yeniden aç).

## 0.11.1 beta
- **DISO tarayıcı eklentisini kendisi önerir:** açıldıktan birkaç saniye sonra, eklenti henüz bir tarayıcıda değilse "DISO'yu tarayıcına ekleyelim mi?" diye sorar. **Eklentiyi ekle** adım adım rehberi açar, **Sonra hatırlat** üç gün sonra tekrar sorar, **Bir daha sorma** hiç sormaz. Eklenti DISO'ya bir kez bağlanınca soru tamamen kalkar. DISO simge olarak başlarsa, tarayıcıdan link alma kapalıysa ya da bilgisayarda desteklenen tarayıcı yoksa sorulmaz.
- Kurulumda, rehberde ve eklentinin ayarlarında eklentiyle ilgili daha açık metinler.

## 0.11.0 beta
**Yeni: tarayıcı eklentisi IDM'inki gibi çalışıyor**
- **DISO kendisi açılır:** tarayıcıda "DISO ile indir" dediğinde DISO kapalıysa eklenti onu başlatır (tarayıcının native messaging kanalıyla, IDM gibi), hazır olmasını bekler ve indirme hemen başlar. Kurulum bunu her tarayıcı için kaydeder; DISO da her açılışta kendini o kullanıcı için kaydeder, böylece taşınabilir `DISO.exe` ile de çalışır. Kaldırınca silinir.
- **Kurulum hangi tarayıcılara eklenti kurulacağını sorar** (Chrome, Edge, Brave, Opera, Vivaldi, Firefox; bilgisayardakiler bulunur ve işaretli gelir), sonra bir rehber açar: tarayıcının eklentiler sayfasını ve eklenti klasörünü açar, klasörün yolunu panoya kopyalar. Aynı rehber DISO'da da var: Ayarlar → **🧩 Tarayıcıya ekle**.
- Eklenti DISO'nun yanına kurulur (`C:\Program Files\ISO\DISO\browser_extension`) ve sabit bir kimliği vardır; güncellemelerde aynı eklenti olarak kalır.
- Sayfanın sağ tık menüsünde **"Bu sayfadaki tüm dosya linklerini DISO ile indir"**.
- Araç çubuğundaki düğme **DISO'nun şu an ne indirdiğini** gösterir (sayı, hız, sıra) ve **▶ DISO'yu aç** düğmesi var; düğmeleri DISO kapalıyken de çalışır.
- Yakalanan tarayıcı indirmeleri DISO açılırken bekler ve ona geçer; DISO açılamazsa tarayıcıda devam eder.
- Eklentide yeni ayar: "DISO kapalıysa aç" (varsayılan açık).

## 0.10.1 beta
**Yeni**
- **Her yerde iki dil:** uygulama, kurulum ve kaldırma pencereleri, tarayıcı eklentisi ve GitHub'daki bütün belgeler (README, sürüm geçmişi, teknik açıklama, eklenti ve FFmpeg notları) Türkçe ve İngilizce.
- İlk açılışta dil Windows'tan seçilir: Windows Türkçe ise Türkçe, değilse İngilizce. Ayarlar → Dil ile istediğin zaman değişir. Kurulum DISO'da seçtiğin dili, eklenti tarayıcının dilini kullanır.
- **✉ Bize ulaş:** Hakkında penceresinde GitHub'da yeni bir sorun sayfası açan düğme. "Bana yolla" yerine artık sorunlar GitHub'dan bildiriliyor.

- Kurulum dosyasının adı artık `DISO-Setup-<sürüm>.exe` (eskiden `DISO-Kurulum-…`), iki dilde de aynı.

**Düzeltildi**
- İngilizce arayüzde Türkçe kalan yazılar: filtre ve sıralama seçenekleri ("Tamamlanan", "Ad (A→Z)"), indirme türü "Ses (MP3)", duraklatılmış satırın durumu, link bilgisindeki "Sadece ses (MP3)" ve altyazı satırı, güncellemelerdeki "Kur" düğmesi ve "Son kontrol", geçmiş penceresindeki "Bugün/Dün", "toplam", "En çok", müzik çaların "Çalmaya hazırlanıyor…" ve "Çalamadım, sıradakine geçtim" notları, şarkı aramadaki hata yazıları.

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
