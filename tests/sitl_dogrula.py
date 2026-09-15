"""
sitl_dogrula.py
----------------
GERCEK ArduPilot SITL'e karsi protokol dogrulama araci.

Otomatik test takimi (`unittest discover`) sahte arac kullanir ve SITL
GEREKTIRMEZ. Bu betik ise farkli bir soruyu cevaplar: gonderdigimiz
komutlara GERCEK otopilotun verdigi yanit, varsayimlarimizla ortusuyor mu?
Ozellikle ivmeolcer kalibrasyonundaki STATUSTEXT metinleri.

Dosya adi "test" ile baslamadigi icin unittest tarafindan toplanmaz.

KULLANIM
--------
1. SITL'i baslatin (MAVProxy GEREKMEZ):

     cd /Applications/projeler/ardupilot
     ./build/sitl/bin/arducopter --model quad \
         --serial0 tcp:5760 \
         --serial1 udpclient:127.0.0.1:14550 \
         --defaults Tools/autotest/default_params/copter.parm

   Iki secenek de onemlidir:
     --serial0 tcp:5760  ":wait" EKLENMEZ. Varsayilan "tcp:5760:wait"
                         oldugu icin SITL, 5760'a biri baglanana kadar
                         BEKLER ve hicbir telemetri yayinlamaz. Ayrica
                         her yeni TCP baglantisinda kendini sifirlar —
                         bu, kalibrasyon gibi cok adimli islemleri yarida
                         keser.
     --serial1 udpclient:127.0.0.1:14550
                         Projenin varsayilan adresinde ayri, kararli bir
                         MAVLink akisi acar.

2. Bu betigi calistirin:

     .venv/bin/python tests/sitl_dogrula.py

   Farkli bir adres icin: SITL_ADRES=tcp:127.0.0.1:5760 ... seklinde.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.drone_telemetry import (
    ACCEL_CAL_POS_FAILED,
    ACCEL_CAL_POS_SUCCESS,
    DroneTelemetry,
    MAG_CAL_STATUS_TEXTS,
)
from ui.calibration_dialog import pozisyon_kodu_bul

ADRES = os.environ.get("SITL_ADRES", "udp:127.0.0.1:14550")

YESIL, KIRMIZI, SARI, SIFIRLA = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
sonuclar = []


def bildir(baslik, gecti, ayrinti=""):
    isaret = f"{YESIL}GECTI{SIFIRLA}" if gecti else f"{KIRMIZI}KALDI{SIFIRLA}"
    print(f"  [{isaret}] {baslik}")
    if ayrinti:
        for satir in str(ayrinti).splitlines():
            print(f"          {satir}")
    sonuclar.append((baslik, gecti))


def topla(drone, saniye, tur=None):
    """Belirtilen sure boyunca telemetri okur, istenen turleri dondurur."""
    bitis = time.time() + saniye
    toplanan = []
    while time.time() < bitis:
        veri = drone.get_telemetry_data()
        if veri and (tur is None or veri.get("type") in tur):
            toplanan.append(veri)
        elif veri is None:
            time.sleep(0.005)
    return toplanan


def bekle(drone, kosul, saniye):
    bitis = time.time() + saniye
    while time.time() < bitis:
        veri = drone.get_telemetry_data()
        if veri and kosul(veri):
            return veri
        if veri is None:
            time.sleep(0.005)
    return None


# --------------------------------------------------------------------------


def dogrula_rtl_alt(drone):
    print(f"\n{SARI}1. RTL irtifa parametresi{SIFIRLA}")
    drone.request_failsafe_params()
    gelenler = topla(drone, 4.0, {"PARAM_VALUE"})
    adlar = {v["param_id"]: v["value"] for v in gelenler}
    rtl = {a: d for a, d in adlar.items() if a.startswith("RTL_ALT")}
    bildir(
        "FC en az bir RTL irtifa parametresi bildirdi",
        bool(rtl),
        f"gelen: {rtl or 'yok'}",
    )

    # Ikisine de yaziyoruz; FC hangisini taniyorsa onu gunceller.
    drone.set_rtl_altitude(25.0)
    time.sleep(1.0)
    drone.request_failsafe_params()
    sonra = {v["param_id"]: v["value"] for v in topla(drone, 4.0, {"PARAM_VALUE"})}
    yeni = {a: d for a, d in sonra.items() if a.startswith("RTL_ALT")}
    beklenen = {"RTL_ALT_M": 25.0, "RTL_ALT": 2500.0}
    dogru = [a for a, d in yeni.items() if abs(d - beklenen.get(a, -1)) < 0.6]
    bildir(
        "RTL irtifasi dogru birimde yazildi (25 m)",
        bool(dogru),
        f"yazma sonrasi: {yeni}",
    )


def dogrula_mission(drone):
    print(f"\n{SARI}2. Gorev yukleme / indirme{SIFIRLA}")
    gorev = [
        (-35.36200, 149.16500, 30.0),
        (-35.36300, 149.16600, 40.0),
        (-35.36400, 149.16700, 25.0),
    ]
    ok, mesaj = drone.upload_mission(gorev)
    bildir("Gorev yuklendi", ok, mesaj)
    if not ok:
        return

    ok, mesaj, geri = drone.download_mission()
    bildir("Gorev geri okundu", ok, f"{mesaj} -> {len(geri)} nokta")
    if not ok:
        return

    eslesme = len(geri) == len(gorev) and all(
        abs(a[0] - b[0]) < 1e-5 and abs(a[1] - b[1]) < 1e-5 and abs(a[2] - b[2]) < 1.0
        for a, b in zip(gorev, geri)
    )
    bildir(
        "Yuklenen ve okunan waypointler ayni (seq=0 home kurali dogru)",
        eslesme,
        f"yuklenen: {gorev}\nokunan:   {geri}",
    )


def dogrula_accel_cal(drone):
    print(f"\n{SARI}3. Ivmeolcer kalibrasyonu{SIFIRLA}")
    print("   NOT: SITL'de arac fiziksel olarak cevrilemedigi icin 6 pozisyonun")
    print("   TAMAMI tamamlanamaz — 2. pozisyonda ornek yanlis olur ve FC")
    print("   'Calibration FAILED' bildirir. Burada dogrulanan sey, FC ile")
    print("   GCS arasindaki PROTOKOL AKISIdir.\n")

    drone.start_accel_cal()

    istekler = []      # FC'nin COMMAND_LONG ile istedigi pozisyonlar
    metinler = []      # "Place vehicle ..." STATUSTEXT'leri
    sonuc_kodu = None
    yanitlanan = set()

    bitis = time.time() + 40
    while time.time() < bitis:
        veri = drone.get_telemetry_data()
        if not veri:
            time.sleep(0.005)
            continue

        if veri["type"] == "ACCEL_CAL_POSITION":
            poz = veri["position"]
            if poz in (ACCEL_CAL_POS_SUCCESS, ACCEL_CAL_POS_FAILED):
                sonuc_kodu = poz
                break
            if poz not in yanitlanan:
                yanitlanan.add(poz)
                istekler.append(poz)
                print(f"          FC pozisyon {poz} istiyor -> yanit gonderiliyor")
                drone.send_accel_cal_position(poz)
                time.sleep(0.4)

        elif veri["type"] == "STATUSTEXT":
            metin = veri.get("text", "")
            if "place" in metin.lower():
                metinler.append(metin)

    bildir(
        "FC pozisyonu COMMAND_LONG / ACCELCAL_VEHICLE_POS ile istedi",
        bool(istekler),
        f"istenen pozisyonlar: {istekler}",
    )
    bildir(
        "Ilk istenen pozisyon LEVEL (1)",
        istekler[:1] == [1],
        f"ilk istek: {istekler[0] if istekler else 'yok'}",
    )
    bildir(
        "Yanit sonrasi FC bir SONRAKI pozisyonu istedi (akis ilerliyor)",
        len(istekler) >= 2,
        f"{len(istekler)} farkli pozisyon istendi",
    )
    if metinler:
        kodlar = [pozisyon_kodu_bul(m) for m in metinler]
        for m, k in zip(metinler, kodlar):
            print(f"          STATUSTEXT {m!r} -> kod {k}")
        bildir(
            "Gelen STATUSTEXT metinleri dogru koda eslendi (yedek kanal)",
            all(k is not None for k in kodlar),
        )
    bildir(
        "FC sonucu bildirdi (SITL'de BASARISIZ beklenir)",
        sonuc_kodu is not None,
        {
            ACCEL_CAL_POS_SUCCESS: "BASARILI",
            ACCEL_CAL_POS_FAILED: "BASARISIZ (SITL'de beklenen)",
        }.get(sonuc_kodu, "sonuc kodu gelmedi"),
    )


def dogrula_mag_cal(drone):
    print(f"\n{SARI}4. Pusula kalibrasyonu{SIFIRLA}")
    drone.start_mag_cal()
    ilerleme = topla(drone, 12.0, {"MAG_CAL_PROGRESS", "MAG_CAL_REPORT"})
    bildir(
        "MAG_CAL_PROGRESS mesajlari geldi",
        any(v["type"] == "MAG_CAL_PROGRESS" for v in ilerleme),
        f"{len(ilerleme)} mesaj",
    )
    durumlar = {v["cal_status"] for v in ilerleme if v["type"] == "MAG_CAL_PROGRESS"}
    bilinen = durumlar.issubset(set(MAG_CAL_STATUS_TEXTS))
    bildir(
        "Bildirilen cal_status degerleri tabloda tanimli",
        bilinen or not durumlar,
        f"gelen durumlar: {sorted(durumlar)}",
    )
    drone.cancel_mag_cal()
    time.sleep(1.0)
    bildir("Iptal komutu gonderildi (istisna yok)", True)


def dogrula_telemetri(drone):
    print(f"\n{SARI}5. Temel telemetri{SIFIRLA}")
    gelen = topla(drone, 6.0)
    turler = {v["type"] for v in gelen}
    for tur in ("HEARTBEAT", "ATTITUDE", "GLOBAL_POSITION_INT", "SYS_STATUS"):
        bildir(f"{tur} cozumlendi", tur in turler)
    hb = [v for v in gelen if v["type"] == "HEARTBEAT"]
    bildir(
        "Ucus modu okundu",
        bool(hb) and hb[-1].get("mode") not in (None, "UNKNOWN"),
        f"mod: {hb[-1].get('mode') if hb else '-'}",
    )


def main():
    print(f"SITL'e baglaniliyor: {ADRES}")
    try:
        drone = DroneTelemetry(ADRES)
    except Exception as e:
        print(f"{KIRMIZI}Baglanti kurulamadi: {e}{SIFIRLA}")
        print("SITL calisiyor mu? Kullanim icin dosyanin basindaki nota bakin.")
        return 1

    try:
        dogrula_telemetri(drone)
        dogrula_rtl_alt(drone)
        dogrula_mission(drone)
        dogrula_accel_cal(drone)
        dogrula_mag_cal(drone)
    finally:
        drone.close()

    gecen = sum(1 for _, g in sonuclar if g)
    print(f"\n{'='*58}")
    print(f"SONUC: {gecen}/{len(sonuclar)} kontrol gecti")
    kalanlar = [b for b, g in sonuclar if not g]
    if kalanlar:
        print(f"{KIRMIZI}Gecmeyenler:{SIFIRLA}")
        for b in kalanlar:
            print(f"  - {b}")
    return 0 if gecen == len(sonuclar) else 1


if __name__ == "__main__":
    sys.exit(main())
