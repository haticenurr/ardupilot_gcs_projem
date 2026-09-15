"""
battery.py
-----------
Pil hesaplari ve "eve donmeye pil yeter mi" tahmini.

`SYS_STATUS.battery_remaining` yalnizca otopilotun yuzde tahminidir ve
pil gerilimine gore hizla sicrar. `BATTERY_STATUS` ise anlik akimi ve
harcanan mAh'i verir; gercek karar bunlarla verilir.

Modul saf fonksiyonlardan olusur: Qt bilmez, MAVLink'e dokunmaz.
"""

# Pilin tamamini harcamak pili kalici olarak yipratir ve inis icin pay
# birakmaz. Eve donus hesabinda bu oran her zaman yedekte tutulur.
VARSAYILAN_YEDEK_ORANI = 0.20

# Bu akimin altindaki degerler "bilinmiyor" sayilir (FC -1 bildirir).
GECERSIZ_AKIM = -0.001


def kalan_mah(kapasite_mah, tuketilen_mah):
    """Pakette kalan mAh. Bilinmeyen degerlerde None doner."""
    if not kapasite_mah or kapasite_mah <= 0:
        return None
    if tuketilen_mah is None or tuketilen_mah < 0:
        return None
    return max(0.0, float(kapasite_mah) - float(tuketilen_mah))


def kalan_ucus_suresi_s(kalan_mah_degeri, akim_a):
    """Mevcut akim cekisiyle kac saniye daha ucabilir.

    saat = kalan_mAh / (akim_A * 1000)  ->  saniye = saat * 3600
    """
    if kalan_mah_degeri is None or akim_a is None or akim_a <= GECERSIZ_AKIM:
        return None
    if akim_a <= 0:
        return None
    return (kalan_mah_degeri / (akim_a * 1000.0)) * 3600.0


def eve_donus_tahmini(
    mesafe_m,
    hiz_ms,
    akim_a,
    kalan_mah_degeri,
    yedek_orani=VARSAYILAN_YEDEK_ORANI,
    kapasite_mah=None,
):
    """Eve donmek icin gereken enerjiyi ve yetip yetmeyecegini hesaplar.

    Donus sozlugu:
      sure_s        : eve donus suresi (saniye)
      gereken_mah   : donus icin gereken enerji
      yedek_mah     : inis/pay icin ayrilan miktar
      kalan_mah     : donus sonrasi beklenen kalan
      yeterli       : yedek dusuldukten sonra yetiyor mu
      hesaplanabildi: girdiler yeterli miydi

    Girdilerden biri bilinmiyorsa `hesaplanabildi=False` doner; arayuz
    bu durumda tahmin yerine "--" gosterir. Eksik veriyle tahmin
    uretmek, pilota yanlis guven verecegi icin bilincli olarak
    yapilmiyor.
    """
    bos = {
        "sure_s": None,
        "gereken_mah": None,
        "yedek_mah": None,
        "kalan_mah": None,
        "yeterli": None,
        "hesaplanabildi": False,
    }
    if mesafe_m is None or mesafe_m < 0:
        return bos
    if not hiz_ms or hiz_ms <= 0:
        return bos
    if akim_a is None or akim_a <= 0:
        return bos
    if kalan_mah_degeri is None:
        return bos

    sure_s = mesafe_m / hiz_ms
    gereken_mah = akim_a * 1000.0 * (sure_s / 3600.0)

    # Yedek, paket kapasitesinin orani olarak hesaplanir; kapasite
    # bilinmiyorsa su anki kalanin orani kullanilir.
    taban = kapasite_mah if kapasite_mah and kapasite_mah > 0 else kalan_mah_degeri
    yedek_mah = taban * yedek_orani

    return {
        "sure_s": sure_s,
        "gereken_mah": gereken_mah,
        "yedek_mah": yedek_mah,
        "kalan_mah": kalan_mah_degeri - gereken_mah,
        "yeterli": (kalan_mah_degeri - gereken_mah) >= yedek_mah,
        "hesaplanabildi": True,
    }


def hucre_sayisi_tahmini(voltaj, hucre_basi_nominal=3.7):
    """Paket gerilimine bakarak hucre sayisini (S) tahmin eder.
    LiPo hucre araligi 3.0-4.35 V oldugu icin tahmin genelde nettir."""
    if not voltaj or voltaj <= 0:
        return None
    tahmin = round(voltaj / hucre_basi_nominal)
    if tahmin < 1:
        return None
    hucre_gerilimi = voltaj / tahmin
    if not 2.8 <= hucre_gerilimi <= 4.4:
        return None
    return tahmin
