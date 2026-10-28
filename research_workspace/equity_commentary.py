"""Rule-based, auditable Turkish commentary for completed research replay bars.

This is intentionally NOT a language-model prediction, trade recommendation,
broker instruction or certified market-data interpretation. Every statement
is computed from the visible replay prefix and the source's declared metadata.
"""
from __future__ import annotations

import math

import pandas as pd

from research_workspace.equity_indicators import indicator_frame
from research_workspace.equity_structure import (
    confirmed_swing_events, confirmed_trendline_segments, structure_state,
)
from research_workspace.equity_volume import volume_frame


def _available(value):
    return value is not None and math.isfinite(float(value))


def _closest_zone(zones: list[dict], kind: str, close: float):
    candidates = [
        z for z in zones if z["kind"] == kind and
        (z["lower"] <= close if kind == "support" else z["upper"] >= close)
    ]
    if not candidates:
        return None

    def distance(z):
        return max(z["lower"] - close, 0, close - z["upper"])

    return min(candidates, key=lambda z: (distance(z), z["id"]))


def commentary_report(prefix: pd.DataFrame, features: dict, metadata: dict) -> dict:
    """Return deterministic, evidence-backed observations; never read future bars."""
    if prefix.empty or len(features["snapshots"]) != len(prefix):
        raise ValueError("Commentary requires a nonempty complete replay prefix")
    if metadata.get("orders_enabled") is not False:
        raise ValueError("Only read-only research sources may be interpreted")
    if metadata.get("feed_verified") is not False:
        raise ValueError("Unverified-source commentary cannot claim a verified feed")

    n = len(prefix)
    close = float(prefix.close.iloc[-1])
    last_end = pd.Timestamp(prefix.bar_end.iloc[-1])
    if last_end.tzinfo is None:
        raise ValueError("Bar-close availability must carry a timezone")
    as_of_ny = last_end.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M %Z")
    events = confirmed_swing_events(features, n)
    state = structure_state(events)
    labels = {"rising": "Yükselen dip ve tepe dizilimi (HH + HL)",
              "falling": "Alçalan tepe ve dip dizilimi (LH + LL)",
              "mixed": "Karışık / net olmayan salınım yapısı",
              "insufficient": "Yeterli sayıda onaylanmış salınım yok"}
    latest = {}
    for e in events:
        latest[e["kind"]] = e

    sections = []
    previous = float(prefix.close.iloc[-2]) if n > 1 else None
    change = (close / previous - 1) * 100 if previous else None
    change_text = (f"Son mum değişimi: %{change:+.2f} (bir önceki tamamlanan muma göre)."
                   if change is not None else "Değişim için önceki mum henüz yok.")
    sections.append({
        "heading": "Fiyat ve gözlem zamanı",
        "text": f"{metadata['symbol']} için {as_of_ny} itibarıyla son tamamlanan mum kapanışı "
                f"{close:.3f} (kaynak birimi). {change_text} Bu günlük getiri değildir.",
    })

    age_text = []
    for kind, label in (("resistance", "tepe"), ("support", "dip")):
        event = latest.get(kind)
        if event:
            age_text.append(
                f"Son onaylı {label}: {event['price']:.3f}, {event['label']} "
                f"(onaydan bu yana {n - 1 - event['confirmed_index']} mum)"
            )
    sections.append({
        "heading": "Piyasa yapısı · onaylanmış dönüşler",
        "text": labels[state] + ". " + ("; ".join(age_text) if age_text else
                 "Henüz kıyaslanabilir iki aynı tür pivot bulunmuyor.") +
                 ". Etiketler yalnızca pivotun onaylandığı kapanıştan itibaren bilinir; "
                 "trendin devamını garanti etmez.",
    })

    indicator = indicator_frame(prefix).iloc[-1]
    e9, e21 = indicator["ema_9"], indicator["ema_21"]
    if _available(e9) and _available(e21):
        if e9 > e21:
            ema_msg = "EMA9, EMA21 üzerinde (kısa vadeli ortalamalarda yukarı sıralama)."
        elif e9 < e21:
            ema_msg = "EMA9, EMA21 altında (kısa vadeli ortalamalarda aşağı sıralama)."
        else:
            ema_msg = "EMA9 ve EMA21 yaklaşık eşit."
        ema_msg += " Son kapanış EMA21 " + ("üzerinde." if close > e21 else
                                            "altında veya seviyesinde.")
    else:
        ema_msg = "EMA9/21 karşılaştırması için yeterli tamamlanmış mum yok."
    rsi = indicator["rsi_14"]
    if _available(rsi):
        area = ("30 altında" if rsi < 30 else "70 üzerinde" if rsi > 70 else
                "30–70 aralığında")
        rsi_msg = f"RSI(14) = {rsi:.1f}, {area}."
    else:
        rsi_msg = "RSI(14) henüz hesaplanamıyor (en az 15 kapanış gerekli)."
    sections.append({
        "heading": "EMA ve momentum",
        "text": ema_msg + " " + rsi_msg + " Bu ölçümler tek başına işlem sinyali değildir.",
    })

    rel = volume_frame(prefix)["relative_volume_20"].iloc[-1]
    if _available(rel):
        if rel >= 1.5:
            vol_msg = "Son mumun hacmi geçmiş 20 muma kıyasla belirgin yüksek."
        elif rel <= 0.75:
            vol_msg = "Son mumun hacmi geçmiş 20 muma kıyasla düşük."
        else:
            vol_msg = "Son mumun hacmi geçmiş 20 mum ortalamasına yakın."
        vol_msg += f" RVOL = {rel:.2f}x."
    else:
        vol_msg = "RVOL henüz yok: önceki 20 mum eksik veya ortalama sıfır."
    sections.append({
        "heading": "Hacim",
        "text": vol_msg + " Günün aynı saatine göre düzeltilmiş değildir; "
                "IEX hacmi tüm ABD piyasasının hacmi değildir.",
    })

    zones = features["snapshots"][-1]["zones"]
    zone_text = []
    for kind, label in (("support", "Destek"), ("resistance", "Direnç")):
        z = _closest_zone(zones, kind, close)
        zone_text.append(
            f"{label}: {z['lower']:.3f}–{z['upper']:.3f} ({z['id']})"
            if z else f"{label}: uygun aktif ve onaylanmış bölge yok"
        )
    sections.append({
        "heading": "Güncel S/R bölgeleri",
        "text": "; ".join(zone_text) +
                ". Yalnızca son mumda etkin olan bölgeler kullanılır; "
                "tarihsel bantlar onaylandıkları zamanlarda gösterilir.",
    })

    lines = confirmed_trendline_segments(features, n)
    line_text = []
    for kind, title in (("support", "Dip trend çizgisi"),
                        ("resistance", "Tepe trend çizgisi")):
        current = [s for s in lines if s["kind"] == kind and s["end_index"] == n - 1]
        if current:
            segment = current[-1]
            direction = ("yukarı" if segment["slope_per_bar"] > 0 else
                         "aşağı" if segment["slope_per_bar"] < 0 else "yatay")
            line_text.append(
                f"{title}: {direction} eğimli, son mekanik çizgi değeri "
                f"{segment['values'][-1]:.3f} (eğim {segment['slope_per_bar']:+.4f}/mum)"
            )
        else:
            line_text.append(f"{title}: iki onaylı pivot henüz yok")
    sections.append({
        "heading": "Mekanik trend çizgileri",
        "text": "; ".join(line_text) +
                ". Çizgiler son iki aynı tür onaylı pivot ile kurulur, "
                "ancak ikinci pivotun onayından önce çizilmez. "
                "Gelecek fiyat tahmini veya kırılma garantisi değildir.",
    })

    feed = metadata.get("feed", "belirtilmemiş")
    source = metadata.get("origin", "Kaynak belirtilmemiş")
    if metadata.get("synthetic") is True:
        source_note = "Sentetik eğitim verisi; gerçek piyasa fiyatı değildir."
    else:
        source_note = "Fiyat kaynağı ve tarihsel erişilebilirlik bağımsız doğrulanmadı."
    sections.append({
        "heading": "Veri güvenilirliği ve kapsam",
        "text": f"Kaynak: {source}. Feed: {feed}. {source_note} "
                "Bu yalnızca geçmiş mumlara dayalı kurallı betimlemedir; "
                "kârlılık, işlem önerisi veya gerçek zamanlı sinyal değildir.",
    })

    return {
        "schema": "tradelab.equity.commentary.v1",
        "as_of_utc": last_end.tz_convert("UTC").isoformat(),
        "symbol": metadata["symbol"],
        "method": "Deterministic, rule-based, replay-prefix only",
        "structure": state,
        "sections": sections,
        "evidence": {
            "visible_bars": n,
            "close": close,
            "ema_9": float(e9) if _available(e9) else None,
            "ema_21": float(e21) if _available(e21) else None,
            "rsi_14": float(rsi) if _available(rsi) else None,
            "relative_volume_20": float(rel) if _available(rel) else None,
            "confirmed_swings": len(events),
            "active_zones": len(zones),
            "source_origin": source,
            "feed": feed,
            "point_in_time_archive_verified": False,
            "orders_enabled": False,
        },
    }
