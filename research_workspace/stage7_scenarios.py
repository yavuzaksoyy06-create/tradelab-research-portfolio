"""Conditional research narratives, never trading recommendations or probability releases."""
from research_workspace.stage7_events import HORIZONS, INSUFFICIENT
from research_workspace.equity_commentary import _closest_zone


def scenarios(record):
    close = record["close"]
    support = _closest_zone(record["zones"], "support", close)
    resistance = _closest_zone(record["zones"], "resistance", close)
    bullish = (f"Onaylı direnç {resistance['upper']:.3f} üzerinde iki tamamlanan kapanış."
               if resistance else "Uygun onaylı direnç yok; fiyat eşiği tanımlanamıyor, senaryo etkin değil.")
    bearish = (f"Onaylı destek {support['lower']:.3f} altında iki tamamlanan kapanış."
               if support else "Uygun onaylı destek yok; fiyat eşiği tanımlanamıyor, senaryo etkin değil.")
    structure = {"rising": "yükselen tepe ve dip", "falling": "alçalan tepe ve dip",
                 "mixed": "karışık tepe/dip dizilimi", "insufficient": "yeterli onaylı pivot yok"}[record["structure"]]
    ema = {1: "EMA9, EMA21 üzerinde", -1: "EMA9, EMA21 altında", 0: "EMA9 ve EMA21 eşit"}[record["ema_sign"]]
    return {
        "as_of": record["observed_at"], "probability": None, "status": INSUFFICIENT,
        "observed_fact": f"Onaylı yapı: {structure}; {ema}. "
                         f"Gözlenen S/R olay sınıfı: {record['event']['type']}.",
        "historical_relationship": "Bu görünümün yön tahmin gücü henüz gerçek veride bağımsız doğrulanmadı.",
        "scenarios": [
            {"name": "Yükseliş / toparlanma", "condition": bullish,
             "invalidation": (f"Kırılma sonrası aynı direnç bölgesinin alt sınırı {resistance['lower']:.3f} altında kapanış."
                              if resistance else "Tanımlı eşik olmadığı için aktif değil."),
             "evidence": "Mevcut onaylı direnç geometrisi; devam sıklığı ve başarı oranı bilinmiyor.",
             "horizons": list(HORIZONS)},
            {"name": "Düşüş / devam", "condition": bearish,
             "invalidation": (f"Kırılma sonrası aynı destek bölgesinin üst sınırı {support['upper']:.3f} üzerinde kapanış."
                              if support else "Tanımlı eşik olmadığı için aktif değil."),
             "evidence": "Mevcut onaylı destek geometrisi; devam sıklığı ve başarı oranı bilinmiyor.",
             "horizons": list(HORIZONS)},
            {"name": "Yatay / net üstünlük yok",
             "condition": "İki kapanışla doğrulanmış kırılma yoksa, bölge sırası belirsizse veya göstergeler çatışıyorsa yön sonucu çıkarılmaz.",
             "invalidation": "Tanımlı bölge dışında iki kapanış gözlenmesi koşullu kırılma senaryosunu etkinleştirir; tahmin gücünü kanıtlamaz.",
             "evidence": "Kalibre edilmiş örneklem dışı kanıt yok; bir sinyalin varlığı tek başına istatistiksel üstünlük değildir.",
             "horizons": list(HORIZONS)},
        ],
        "uncertainty": "Gelecek mum sırası, haberler ve tüm piyasa likiditesi bilinmiyor. Bu fiyat hedefi veya işlem önerisi değildir.",
    }
