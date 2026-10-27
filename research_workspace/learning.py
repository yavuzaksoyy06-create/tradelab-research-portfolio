"""Static hypothetical explanations, separate from measured research evidence."""
TOPICS={
 'Destek ve direnç':'Geçmişte fiyatın tepki verdiği bölgelerdir; kesin dönüş garantisi değildir. Örnek: varsayımsal 98–100 bölgesinde birkaç tepki, tek bir kusursuz çizgiden daha dürüst bir gösterimdir.',
 'Piyasa yapısı':'Yükselen tepe/dipler ve düşen tepe/dipler trend yapısını betimler. Bir swing noktası ancak sonraki mumlar teyit ettiğinde biliniyor olabilir; geçmişe erken işaret koymak bilgi sızıntısı yaratır.',
 'Beklenen değer':'Hipotetik örnek: kazanma olasılığı %40, ortalama kazanç 2R, ortalama kayıp 1R ise E[R] = 0,40×2 − 0,60×1 = 0,20R. Her işlem maliyeti 0,10R ise net beklenti 0,10R olur. Bu bir veri sonucu değildir.',
 'Kazanma oranı ve kazanç/kayıp oranı':'%70 başarı, ortalama kazanç 0,3R ve kayıp 1R ile 0,70×0,3 − 0,30×1 = −0,09R verir (maliyet öncesi). Yüksek kazanma oranı tek başına yeterli değildir.',
 'ATR ve oynaklık':'True Range = max(yüksek−düşük, |yüksek−önceki kapanış|, |düşük−önceki kapanış|). ATR bunun belirli bir yumuşatmayla ortalamasıdır; yön tahmini değildir. Periyot ve yumuşatma yöntemi belirtilmelidir.',
 'Spread ve slippage':'Spread alış/satış kotasyon farkıdır. Slippage beklenen ve gerçekleşen fiyat farkıdır; yönü olumlu veya olumsuz olabilir. Sentetik ham fiyat getirisi bunları içermez.',
 'Drawdown ve logaritmik büyüme':'Zirve 100 iken değer 80 ise düşüş %20; 100’e dönmek için %25 artış gerekir. +%10 sonra −%10: 1,10×0,90=0,99, toplam −%1. Log büyüme ln(1,10)+ln(0,90)=ln(0,99)≈−0,01005; pozitif servet gerektirir.',
 'Trend ve ortalamaya dönüş':'Trend takibi hareketin sürmesini, ortalamaya dönüş sapmanın azalmasını araştırır. Rejim ve maliyetler sonuçları değiştirir; ikisi de burada öneri veya doğrulanmış strateji değildir.',
 'Look-ahead bias':'Karar anında henüz bilinmeyen kapanışı, revize veriyi veya gelecekte teyit edilmiş swing noktasını kullanmak sonucu iyimserleştirir. Bu laboratuvar fiyatları erişilebilirlik zamanı ile filtreler.',
 'Overfitting':'Çok sayıda kuralı aynı örneklemde deneyip en iyisini seçmek tesadüfü başarı gibi gösterebilir. Ayrılmış dönem, önceden belirlenmiş protokol ve çoklu deneme disiplini gerekir.'
}
