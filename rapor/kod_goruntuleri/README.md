# Kaynak Kod Ekran Goruntuleri

Raporun "Kaynak Kodlar" ekine konulmak uzere uretilmis 12 gorsel.
Gorseller `rapor/kod_goruntusu_uret.py` ile kaynak dosyalardan otomatik
cikarilir; kod degisirse betigi tekrar calistirmak yeterlidir.

    python rapor/kod_goruntusu_uret.py

## Hangi gorsel neyin?

| # | Dosya | Icerik | Kaynak | Satir |
|---|---|---|---|---|
| 1 | `01_alan_tarama_algoritmasi.png` | Alan tarama rotasi uretimi (boustrophedon) | `core/mission_planner.py` | 166–234 |
| 2 | `02_genisleyen_kare_deseni.png` | Genisleyen kare arama deseni | `core/mission_planner.py` | 242–271 |
| 3 | `03_kamera_hat_araligi_ve_izdusum.png` | Kamera FOV'undan hat araligi + yerel duzlem izdusumu | `core/mission_planner.py` | 86–101, 34–47 |
| 4 | `04_gorev_guvenlik_analizi.png` | Gorev olcumleri ve guvenlik denetimleri | `core/mission_analysis.py` | 31–161 (ilk 52 satir) |
| 5 | `05_eve_donus_menzili.png` | Eve donus enerjisi ve yeterlilik hesabi | `core/battery.py` | 42–97 |
| 6 | `06_gorev_yukleme_protokolu.png` | MAVLink gorev yukleme, seq=0 home kurali | `core/drone_telemetry.py` | 648–738 (ilk 52 satir) |
| 7 | `07_telemetri_akitan_bekleme.png` | Protokol beklerken telemetriyi akitma | `core/drone_telemetry.py` | 492–508, 510–522 |
| 8 | `08_telemetri_is_parcacigi.png` | TelemetryWorker ana dongusu | `main_v7.py` | 245–315 (ilk 48 satir) |
| 9 | `09_mavlink2_diyalekt_secimi.png` | MAVLink 2 diyalekt secimi (tam dosya) | `core/mavlink_env.py` | 1–54 |
| 10 | `10_waypoints_disa_aktarma.png` | QGC WPL 110 (.waypoints) uretimi | `core/exporters.py` | 27–59 |
| 11 | `11_kalibrasyon_pozisyon_kanali.png` | Ivmeolcer pozisyon istegi isleme | `ui/calibration_dialog.py` | 414–440 |
| 12 | `12_ornek_testler.png` | Rota uretim testlerinden uc ornek | `tests/test_mission_planner.py` | 120–127, 141–156, 158–169 |

4, 6 ve 8 numarali parcalar uzun oldugu icin kirpilmistir; gorselin
sonunda "... (devami ... icinde)" notu bulunur.

## Neden bu 12 parca?

Secim, projenin ozunu olusturan yerlere gore yapildi:

- **1, 2, 3** — projenin ozgun algoritmalari (rota uretimi)
- **4, 5** — guvenlik hesaplari (gorev denetimi, eve donus menzili)
- **6, 7, 9, 10, 11** — MAVLink protokol islemleri
- **8** — es zamanlilik yapisi (arayuz / MAVLink ayrimi)
- **12** — test yaklasimi

## Word'e eklerken

Gorseller 770–880 piksel genisligindedir. Word'de sayfa genisligine
yaymak yerine yaklasik 14–15 cm genislikte kullanmak, yazi boyutunu
okunur tutar. Sekil aciklamalari sekillerin ALTINA, ortalanmis olarak
yazilmalidir (staj yonergesi RP-023).
