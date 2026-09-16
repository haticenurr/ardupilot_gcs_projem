"""
kod_goruntusu_uret.py
----------------------
Raporun "Kaynak Kodlar" ekine konulmak uzere, projenin secilmis kod
parcalarini sozdizimi renklendirmeli PNG goruntuleri olarak uretir.

Kod parcalari elle kopyalanmaz: her biri kaynak dosyadan FONKSIYON ADIYLA
cikarilir. Boylece kod degisince goruntuler yeniden uretildiginde guncel
kalir ve rapora yanlislikla eski bir surum girmez.

KULLANIM
--------
    python rapor/kod_goruntusu_uret.py

Cikti: rapor/kod_goruntuleri/NN_aciklama.png
"""

import os
import sys

from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import PythonLexer

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEDEF = os.path.join(KOK, "rapor", "kod_goruntuleri")

# Baskida da okunur kalmasi icin acik zeminli stil ve buyuk punto.
BICIMLENDIRICI = dict(
    font_name="Menlo",
    font_size=17,
    line_numbers=True,
    line_number_bg="#f2f2ef",
    line_number_fg="#9a9a95",
    line_number_separator=True,
    line_pad=3,
    style="default",
)


def parca_cikar(dosya, ad, azami_satir=None):
    """Bir fonksiyonu/metodu kaynak dosyadan girinti takip ederek cikarir.

    `ad` bir fonksiyon adi ("survey_grid") olabilir; sinif icindeki
    metotlar da ayni sekilde bulunur. Girinti seviyesi `def` satirindan
    okunur ve govde, bu seviyeye geri donulene kadar alinir.
    """
    yol = os.path.join(KOK, dosya)
    with open(yol, encoding="utf-8") as f:
        satirlar = f.read().split("\n")

    bas = None
    for i, s in enumerate(satirlar):
        if s.lstrip().startswith(f"def {ad}("):
            bas = i
            break
    if bas is None:
        sys.exit(f"'{ad}' bulunamadi: {dosya}")

    girinti = len(satirlar[bas]) - len(satirlar[bas].lstrip())

    # Imza birden fazla satira yayilmis olabilir; govde, parantezler
    # kapandiktan SONRA baslar. Bu kontrol olmadan cok satirli imzanin
    # kapanis parantezi ")" govde sonu sanilip fonksiyon yarim aliniyordu.
    denge = 0
    govde_bas = bas
    for i in range(bas, len(satirlar)):
        denge += satirlar[i].count("(") - satirlar[i].count(")")
        if denge <= 0 and satirlar[i].rstrip().endswith(":"):
            govde_bas = i
            break

    son = len(satirlar)
    for i in range(govde_bas + 1, len(satirlar)):
        s = satirlar[i]
        if not s.strip():
            continue
        if (len(s) - len(s.lstrip())) <= girinti:
            son = i
            break

    parca = satirlar[bas:son]
    while parca and not parca[-1].strip():
        parca.pop()
    # Sinif icindeki metotlarda bastaki 4 bosluk kirpilir
    if girinti:
        parca = [s[girinti:] if s.startswith(" " * girinti) else s for s in parca]
    if azami_satir and len(parca) > azami_satir:
        parca = parca[:azami_satir] + ["", f"# ... (devami {dosya} icinde)"]
    return "\n".join(parca)


def dosya_cikar(dosya, bas_satir=1, azami_satir=None):
    """Bir dosyanin tamamini (veya bas kismini) dondurur."""
    yol = os.path.join(KOK, dosya)
    with open(yol, encoding="utf-8") as f:
        satirlar = f.read().split("\n")
    parca = satirlar[bas_satir - 1:]
    while parca and not parca[-1].strip():
        parca.pop()
    if azami_satir and len(parca) > azami_satir:
        parca = parca[:azami_satir] + ["", f"# ... (devami {dosya} icinde)"]
    return "\n".join(parca)


def goruntu_uret(ad_no, baslik, kod):
    os.makedirs(HEDEF, exist_ok=True)
    png = highlight(kod, PythonLexer(), ImageFormatter(**BICIMLENDIRICI))
    dosya_adi = f"{ad_no:02d}_{baslik}.png"
    yol = os.path.join(HEDEF, dosya_adi)
    with open(yol, "wb") as f:
        f.write(png)
    satir = kod.count("\n") + 1
    print(f"  {dosya_adi:46} {satir:3} satir")
    return dosya_adi


# Rapora konulacak 12 kod parcasi: projenin ozunu olusturan algoritmalar,
# protokol islemleri, es zamanlilik yapisi ve test ornekleri.
PARCALAR = [
    (1, "alan_tarama_algoritmasi",
     lambda: parca_cikar("core/mission_planner.py", "survey_grid")),
    (2, "genisleyen_kare_deseni",
     lambda: parca_cikar("core/mission_planner.py", "expanding_square")),
    (3, "kamera_hat_araligi_ve_izdusum",
     lambda: parca_cikar("core/mission_planner.py", "spacing_from_camera")
             + "\n\n\n"
             + parca_cikar("core/mission_planner.py", "to_local")
             + "\n\n"
             + parca_cikar("core/mission_planner.py", "to_latlon")),
    (4, "gorev_guvenlik_analizi",
     lambda: parca_cikar("core/mission_analysis.py", "analyze_mission",
                         azami_satir=52)),
    (5, "eve_donus_menzili",
     lambda: parca_cikar("core/battery.py", "eve_donus_tahmini",
                         azami_satir=50)),
    (6, "gorev_yukleme_protokolu",
     lambda: parca_cikar("core/drone_telemetry.py", "upload_mission",
                         azami_satir=52)),
    (7, "telemetri_akitan_bekleme",
     lambda: parca_cikar("core/drone_telemetry.py", "_recv_match_pumped")
             + "\n\n\n"
             + parca_cikar("core/drone_telemetry.py", "_drain_pending")),
    (8, "telemetri_is_parcacigi",
     lambda: parca_cikar("main_v7.py", "run", azami_satir=48)),
    (9, "mavlink2_diyalekt_secimi",
     lambda: dosya_cikar("core/mavlink_env.py")),
    (10, "waypoints_disa_aktarma",
     lambda: parca_cikar("core/exporters.py", "mission_to_waypoints")),
    (11, "kalibrasyon_pozisyon_kanali",
     lambda: parca_cikar("ui/calibration_dialog.py",
                         "on_accel_position_request")),
    (12, "ornek_testler",
     lambda: parca_cikar("tests/test_mission_planner.py",
                         "test_rota_poligon_disina_tasmaz")
             + "\n\n"
             + parca_cikar("tests/test_mission_planner.py",
                           "test_hat_araligi_istenen_degere_esit")
             + "\n\n"
             + parca_cikar("tests/test_mission_planner.py",
                           "test_gidis_donus_deseni")),
]


def main():
    print(f"Kod goruntuleri uretiliyor -> {HEDEF}\n")
    for no, baslik, uret in PARCALAR:
        goruntu_uret(no, baslik, uret())
    print(f"\n  toplam {len(PARCALAR)} goruntu")


if __name__ == "__main__":
    main()
