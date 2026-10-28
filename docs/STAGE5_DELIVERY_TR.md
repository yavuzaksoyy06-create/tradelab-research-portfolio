# Stage 5 teslim raporu — 28 Ekim 2026

## Sonuç

Çalışma ec6f9f6 commit'inden devam etti; proje yeniden kurulmadı. Başlangıç kaynak
ZIP'i ve hash listesi yayın alanı dışında saklandı. GitHub checkpoint'leri:

1. d1a5c29 — ayrı namespace kullanan çevrimdışı Treasury v2 normalizer ve 10 test.
2. faa90de — finansal hesaplamalar, CSV ve üç işlevsel Streamlit görünümü; 23 test.
3. Son belge/kabul checkpoint'i — gerçek ekranlar, yöntem ve bütünlük kanıtları.

## Veri düzeltmesi

Eski regex yalnızca tam sayılı vade adlarını kabul ettiği için BC_1_5MONTH kayboluyordu.
Yeni uygulama 14 vadeyi açıkça tanımlar; başlangıç tarihini, null/eksik alan ayrımını,
tekrarları, tarihi, birimi ve sayısal değerleri denetler. BC_30YEARDISPLAY bağımsız
vade sayılmaz. Doğrulanmış aynı XML'den 218 gözlem geri kazanıldı: 3.237 → 3.455.
Eski sürüm kendi doğrulayıcısıyla halen 3.237 gözlem verir. Yeni sürüm ayrı pin,
manifest, kod hash'leri ve üst sürüm manifest bağlantısı taşır. Yeni veri indirilmedi.

## Finansal analizler

Treasury ekranı seçilen tarihlerde gözlenen vade noktalarını, 10Y−2Y ve 10Y−3M
farklarını, negatif farkla tanımlanan ters eğriyi ve baz puan değişimlerini gösterir.
Faiz değişimi tahvil toplam getirisi veya kâr diye sunulmaz. Eksik değerler doldurulmaz.

ECB ekranı EUR/USD, EUR/GBP, EUR/JPY ve mevcut diğer doğrulanmış serileri destekler.
Basit yüzde değişim, log değişim, seçilen başlangıca göre kümülatif değişim ve tam
pencere gerektiren örneklem standart sapması hesaplanır. Volatilite yıllıklandırılmaz.
Kurun yönü, gözlem aralıkları ve bilgi erişilebilirliği belirtilir. CSV'ler sürüm,
pin, kaynak ve dönüşüm bilgilerini taşır.

Örnek gerçek betimsel sonuçlar: 31 Aralık 2025'te 10Y−2Y yaklaşık +71 bp, 10Y−3M
+51 bp. EUR/USD için 26 Ekim 2026 gözlemi 1,1188; önceki gözlenen güne değişim
−%0,04467. Bunlar farklı dönemlerin referans istatistikleridir, yatırım tavsiyesi
veya işlem getirisi değildir. Dönemler örtüşmediğinden ortak korelasyon üretilmedi;
ekran INSUFFICIENT OVERLAPPING VERIFIED DATES gösterir.

## Testler ve korunma

Son tam çalıştırma: 379 test, 378 başarılı, 1 Windows sembolik bağlantı izni nedeniyle
atlandı. Çalışma alanında 133, makroda 115, cryptoda 100, FX'te 31 test gerçekten
çalıştırıldı; eski sayılar toplanmadı. Tam zamanlar public_test_results.json içindedir.
Bir ara UI testi genel kenar çubuğu bilgi kutusunu sayıyordu; gerçek veri etiketini
kontrol edecek şekilde düzeltildi ve tam regresyon tekrar geçti.

Başlangıçta hash'i alınan 2.415 orijinal kaynak/veri dosyası değişmedi. Mevcut koruma
manifestindeki 1.393 dosya ayrıca doğrulandı. V4.1 ve 21 Ocak 2027 21:15 UTC kapısı
korundu; değerlendirme kapalı. Hiçbir gerçek, kâğıt veya replay emri gönderilmedi.

## Sınırlar ve sonraki işler

SHA-256 yerel bütünlüğü gösterir; bağımsız dış denetim veya yayıncı imzası değildir.
Treasury referansı geçmiş 2025 yayın günleridir; geleceğin tatil takvimi değildir.
ECB kapsamı gözlenen referans aralığıyla sınırlıdır. Yeni türevin erişilebilirlik
zamanı türetme anıdır; geçmişe dönük bilgi tarihi üretilmez. Veri klasörleri ve ham
XML GitHub'a yüklenmedi. Yalnızca kaynaklar, testler, belgeler ve iki gerçek ekran
paylaşıldı. Üretim dağıtımı, tahmin doğruluğu, kârlılık ve müşteri etkisi iddia edilmez.

Daha ileri ortak analiz için örtüşen dönem, tanım uyumu ve ayrı tarihsel vintage
kanıtı gerekir. Yeni indirme bu aşamada yetkilendirilmedi ve otomatik yapılmadı.
