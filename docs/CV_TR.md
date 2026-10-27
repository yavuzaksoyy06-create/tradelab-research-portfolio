# Türkçe proje özeti ve CV kullanımı

## Proje adı

**TradeLab — Denetlenebilir Nicel Araştırma ve Veri Doğrulama Platformu**

Finansal araştırmada veri kalitesi, bilgi erişim zamanı, deney tekrarlanabilirliği
ve sonuçların dürüst raporlanması üzerine geliştirilen Python projesi. Streamlit
arayüzü; sentetik öğretici deneyleri, gerçek günlük kamu verisini ve dondurulmuş
tarihsel araştırmayı birbirinden ayırır.

## CV için kısa metin

**TradeLab | Python, pandas, NumPy, Streamlit, Plotly, SQLite**

- Takvim ve saat dilimi farklarını dikkate alan veri doğrulama, SHA-256 kaynak kayıtları ve üzerine yazılmayan veri sürümleri içeren araştırma çalışma alanı geliştirdim.
- Zaman sıralı deneyler, eşleştirilmiş zamanlama kontrolleri, blok bootstrap ve örneklem yeterliliği kontrolleriyle nicel araştırma sonuçlarını değerlendirdim; kanıtlanmamış performans iddialarını rapordan ayırdım.
- ECB ve ABD Hazinesi günlük kamu verilerini kaynak/indirme zamanı ve hash manifestleriyle bağladım; sonuçları etkileşimli grafikler ve denetim ekranlarında sundum.

Bu ifadeleri yalnızca yöntemleri mülakatta kendi sözlerinle açıklayabiliyorsan
kullan. Test sayısını yazacaksan `evidence/public_test_results.json` içindeki
güncel sonuçla sınırla; farklı tarih ve kapsamların sayılarını toplayıp tek bir
test koşusu gibi sunma.

## SnA ilanıyla bağlantı

| İlandaki beklenti | Projede gösterilebilen kanıt | Açık kalan taraf |
|---|---|---|
| Python/R | Python veri işleme, doğrulama, test ve görselleştirme | R kullanımı iddia edilmiyor |
| Uygulamalı istatistik | Kontrol karşılaştırmaları, bootstrap, örneklem sınırları | Çok değişkenli tahmin modeli henüz yok |
| Veritabanı/SQL | SQLite metadata tablosu ve parametreli sorgu kullanımı | İleri SQL/ilişkisel modelleme sınırlı |
| Araştırma ve sorumluluk | Kaynak kayıtları, zaman kapısı, negatif sonuçların korunması | Bağımsız dış denetim iddia edilmiyor |
| İletişim/sunum | Türkçe öğrenme modu, grafikler, karar ve veri reddi açıklamaları | Gerçek müşteri sunumu iddia edilmiyor |

## Mülakatta anlatılabilecek kararlar

1. Bir pivotu oluştuğu anda değil, doğrulanabildiği anda kullanmak neden önemli?
2. Eksik veri neden otomatik doldurulmadı?
3. Bağımsız hesapların kârlarını toplamak neden ortak portföy simülasyonu değildir?
4. Bootstrap aralığının sıfırı içermesi hangi iddiayı engeller?
5. SHA-256 neden kaynak doğruluğu veya yayıncı imzası sayılmaz?
6. Bugün indirilen 2025 verisi neden 2025'te bilinen değer olarak kabul edilmez?
7. Bir hipotezin desteklenmemesi neden yine de değerli bir araştırma sonucudur?

Proje AI destekli geliştirilmiştir. Bu katkıyı gizlemek veya yapılmamış müşteri,
ML ya da ileri SQL deneyimi eklemek yerine hangi tasarım kararlarını verdiğini,
hangi testleri çalıştırdığını ve sınırlamaları nasıl yönettiğini anlat.
