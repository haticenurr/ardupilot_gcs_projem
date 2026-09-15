"""
mission_analysis.py
--------------------
Gorev drona YUKLENMEDEN once yapilan onizleme ve guvenlik analizi.

Amac: pilotun "yukle" demeden once gorevin ne kadar surecegini, ne kadar
uzaga gidecegini ve bir guvenlik sinirini ihlal edip etmedigini gormesi.
Bir waypoint'i yanlislikla geofence disina koymak, ucus sirasinda
failsafe tetiklendiginde anlasilan turden bir hatadir; burada once
yakalanir.

Modul saf fonksiyonlardan olusur: Qt bilmez, MAVLink'e dokunmaz.
"""

from core.mission_planner import haversine_m, point_in_polygon

# Bu mesafeden yakin ardisik noktalar, muhtemelen yanlis tiklamadir.
YAKIN_NOKTA_ESIGI_M = 3.0

# Varsayilan seyir hizi (ArduCopter WPNAV_SPEED varsayilani 5 m/s).
VARSAYILAN_HIZ_MS = 5.0

HATA = "hata"
UYARI = "uyari"


def _uyari(seviye, metin):
    return {"seviye": seviye, "metin": metin}


def analyze_mission(waypoints, home=None, speed_ms=VARSAYILAN_HIZ_MS, fence=None):
    """Gorevi olcer ve guvenlik ihlallerini listeler.

    waypoints : [(lat, lon, alt), ...]
    home      : (lat, lon) — bilinmiyorsa None
    speed_ms  : seyir hizi (m/s)
    fence     : {"enabled": bool, "radius_m": float, "alt_max_m": float,
                 "polygon": [(lat, lon), ...]} — hepsi opsiyonel

    Donus: olcumler ve `uyarilar` listesi iceren sozluk. Uyarilar
    {"seviye": "hata"|"uyari", "metin": str} bicimindedir; "hata"
    seviyesi yuklemeden once mutlaka gozden gecirilmelidir.
    """
    fence = fence or {}
    uyarilar = []

    if not waypoints:
        return {
            "waypoint_sayisi": 0,
            "toplam_mesafe_m": 0.0,
            "bacak_mesafeleri_m": [],
            "tahmini_sure_s": 0.0,
            "eve_en_uzak_m": None,
            "donus_mesafesi_m": None,
            "min_irtifa_m": None,
            "max_irtifa_m": None,
            "uyarilar": [_uyari(HATA, "Gorevde hic waypoint yok")],
        }

    # --- mesafeler ---
    bacaklar = []
    if home is not None:
        bacaklar.append(
            haversine_m(home[0], home[1], waypoints[0][0], waypoints[0][1])
        )
    for onceki, sonraki in zip(waypoints, waypoints[1:]):
        bacaklar.append(
            haversine_m(onceki[0], onceki[1], sonraki[0], sonraki[1])
        )

    toplam = sum(bacaklar)
    hiz = speed_ms if speed_ms and speed_ms > 0 else VARSAYILAN_HIZ_MS
    tahmini_sure = toplam / hiz

    # --- eve uzaklik ---
    eve_en_uzak = None
    donus_mesafesi = None
    if home is not None:
        uzakliklar = [
            haversine_m(home[0], home[1], wp[0], wp[1]) for wp in waypoints
        ]
        eve_en_uzak = max(uzakliklar)
        donus_mesafesi = uzakliklar[-1]

    irtifalar = [float(wp[2]) for wp in waypoints]

    # --- guvenlik kontrolleri ---
    fence_acik = bool(fence.get("enabled"))
    yaricap = fence.get("radius_m")
    alt_max = fence.get("alt_max_m")
    poligon = fence.get("polygon") or []

    for i, (lat, lon, alt) in enumerate(waypoints, start=1):
        if alt <= 0:
            uyarilar.append(
                _uyari(HATA, f"Waypoint {i}: irtifa {alt:.0f} m — sifir veya negatif")
            )
        if alt_max and alt > alt_max:
            uyarilar.append(
                _uyari(
                    HATA,
                    f"Waypoint {i}: irtifa {alt:.0f} m, FENCE_ALT_MAX "
                    f"({alt_max:.0f} m) asiliyor",
                )
            )
        if fence_acik and yaricap and home is not None:
            uzaklik = haversine_m(home[0], home[1], lat, lon)
            if uzaklik > yaricap:
                uyarilar.append(
                    _uyari(
                        HATA,
                        f"Waypoint {i}: eve {uzaklik:.0f} m — dairesel geofence "
                        f"({yaricap:.0f} m) disinda",
                    )
                )
        if poligon and len(poligon) >= 3 and not point_in_polygon(lat, lon, poligon):
            uyarilar.append(
                _uyari(HATA, f"Waypoint {i}: poligon geofence disinda")
            )

    # Yanlis tiklama suphesi
    for i, mesafe in enumerate(
        [
            haversine_m(a[0], a[1], b[0], b[1])
            for a, b in zip(waypoints, waypoints[1:])
        ],
        start=1,
    ):
        if mesafe < YAKIN_NOKTA_ESIGI_M:
            uyarilar.append(
                _uyari(
                    UYARI,
                    f"Waypoint {i} ve {i + 1} birbirine {mesafe:.1f} m uzaklikta "
                    f"— yanlis tiklama olabilir",
                )
            )

    if home is None:
        uyarilar.append(
            _uyari(
                UYARI,
                "Home konumu bilinmiyor — mesafe ve geofence kontrolleri "
                "kalkis noktasina gore yapilamadi",
            )
        )
    if fence_acik and not yaricap and not poligon:
        uyarilar.append(
            _uyari(UYARI, "Geofence acik ama yaricap/poligon bilgisi okunamadi")
        )

    return {
        "waypoint_sayisi": len(waypoints),
        "toplam_mesafe_m": toplam,
        "bacak_mesafeleri_m": bacaklar,
        "tahmini_sure_s": tahmini_sure,
        "eve_en_uzak_m": eve_en_uzak,
        "donus_mesafesi_m": donus_mesafesi,
        "min_irtifa_m": min(irtifalar),
        "max_irtifa_m": max(irtifalar),
        "uyarilar": uyarilar,
    }


def sure_metni(saniye):
    """Saniyeyi 'dd:ss' veya 'ss:dd:ss' bicimine cevirir."""
    saniye = int(round(saniye))
    saat, kalan = divmod(saniye, 3600)
    dakika, sn = divmod(kalan, 60)
    if saat:
        return f"{saat}:{dakika:02d}:{sn:02d}"
    return f"{dakika:02d}:{sn:02d}"


def mesafe_metni(metre):
    """Metreyi okunabilir bicime cevirir (1 km ustunde km kullanir)."""
    if metre is None:
        return "--"
    if metre >= 1000:
        return f"{metre / 1000:.2f} km"
    return f"{metre:.0f} m"


def ozet_metni(analiz):
    """Analizi tek satirlik ozet haline getirir (durum cubugu icin)."""
    return (
        f"{analiz['waypoint_sayisi']} nokta · "
        f"{mesafe_metni(analiz['toplam_mesafe_m'])} · "
        f"~{sure_metni(analiz['tahmini_sure_s'])}"
    )


def hata_sayisi(analiz):
    return sum(1 for u in analiz["uyarilar"] if u["seviye"] == HATA)
