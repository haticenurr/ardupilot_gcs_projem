# GCS v7 — Yer Kontrol Istasyonu

PyQt5 + MAVLink tabanli otonom ucus yer istasyonu. Ana giris: `main_v7.py`.

## Gelistirme kurulumu

Python 3.8+ onerilir. Sanal ortam kullanmak tavsiye edilir:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python main_v7.py
```

Ilk calistirmada `logs/` klasoru (ucus CSV kayitlari) otomatik olusur.
`logs/` ve `__pycache__` repoya dahil degildir (bkz. `.gitignore`) - ucus
kayitlari kullaniciya ozel veridir.

## Testler

Testler gercek bir ucus kontrolcusu veya SITL gerektirmez: ayni makinede UDP
uzerinden konusan sahte bir arac (`tests/test_drone_telemetry.py` icindeki
`FakeVehicle`) HEARTBEAT, telemetri ve gorev protokolu yaniti uretir.

```bash
python -m unittest discover -s tests -v
```

Kapsam: MAVLink katmani, ucus ozeti butonu, kalibrasyon sihirbazi,
disa aktarma bicimleri, sesli uyarilar ve RSSI gostergesi. GUI testleri
Qt'yi ekransiz (`QT_QPA_PLATFORM=offscreen`) calistirir ve sesli uyarilari
sahte bir arka uca yonlendirir — test sirasinda bilgisayar konusmaz.

> Acma ve test adimlarinin tamami icin: **[TEST_REHBERI.md](TEST_REHBERI.md)**

## Ozellikler

| Ozellik | Nerede |
|---|---|
| Canli telemetri, harita, yapay ufuk | Telemetri sekmesi |
| Ucus oncesi kontrol listesi, PreArm/EKF/sensor durumu | Guvenlik paneli |
| Gorev plani (waypoint) yukleme/indirme, otonom gorev sihirbazi | Ucus Plani sekmesi |
| Dairesel ve poligon geofence | Guvenlik paneli + harita |
| **Son Ucus Ozeti** (DISARM sonrasi butonla acilir) | Komuta ve Kontrol |
| **Kalibrasyon sihirbazi** (pusula / ivmeolcer / level / gyro / baro) | Ust cubuk → Kalibrasyon |
| **`.waypoints` ve `.kml` disa aktarma** | Ucus Plani → Disa Aktar · Replay → KML |
| **Sesli uyarilar (TTS)** | Ust cubuk → SES |
| **Telemetri sinyal gucu (RSSI)** | Telemetri kartlari |
| Parametre editoru | Ust cubuk → Parametreler |
| Ucus kaydi (CSV) ve replay | Replay paneli |

### Son Ucus Ozeti

Ozet penceresi DISARM aninda **kendiliginden acilmaz**. RTL/LAND gibi
surecler kisa sureli, gercek olmayan bir DISARM gorunumu uretebildigi
icin pencere beklenmedik anlarda aciliyordu. Ucus bitince ozet saklanir
ve `SON UCUS OZETI (ss:dd)` butonu aktiflesir; pilot hazir oldugunda acar.

### Kalibrasyon

Ust cubuktaki **Kalibrasyon** butonu pusula, ivmeolcer, yatay duzlem,
jiroskop ve barometre kalibrasyonlarini adim adim yonetir. Mission
Planner'a ihtiyac yoktur.

- **Pusula:** araci her eksende cevirin, ilerleme yuzdesi canli gorunur.
  Sonuc `autosave=0` ile alinir — yani **siz "KABUL ET" demeden otopilota
  yazilmaz**.
- **Ivmeolcer:** 6 pozisyon (duz, sol yan, sag yan, burun asagi, burun
  yukari, sirt ustu) sirayla istenir.

Guvenlik: kalibrasyon **yalnizca DISARM haldeyken** baslatilabilir.

### Disa aktarma

- **Ucus Plani → Disa Aktar**: gorevi `.waypoints` (QGC WPL 110 — Mission
  Planner ve QGroundControl okur) veya `.kml` (Google Earth) olarak kaydeder.
- **Replay → KML**: secili CSV ucus kaydini Google Earth icin `.kml`e cevirir.

### Sesli uyarilar

Kritik durumlar (dusuk pil, geofence ihlali, baglanti kaybi, ARM/DISARM,
kritik otopilot mesajlari) sesli anons edilir. Ek Python bagimliligi
gerekmez; isletim sisteminin kendi araci kullanilir:

| Sistem | Kullanilan arac |
|---|---|
| macOS | `say` (yuklu Turkce ses varsa otomatik secilir) |
| Linux | `spd-say`, yoksa `espeak-ng` / `espeak` |
| Windows | PowerShell `System.Speech` |

Hicbiri yoksa buton `SES: YOK` gorunur ve ozellik sessizce devre disi
kalir. Ayni uyari bekleme suresi dolmadan tekrarlanmaz.

## SITL ile test

ArduCopter SITL ornegi (ayri bir terminalde):

```bash
sim_vehicle.py -v ArduCopter --map --console
```

GCS varsayilan UDP adresi: `udp:127.0.0.1:14550`

1. GCS'i acin, baglanti rozetinin **BAGLI** oldugunu kontrol edin.
2. **Ucus Oncesi Kontrol Listesi** ile GPS/EKF/PreArm durumuna bakin.
3. ARM onayindan sonra ozet penceresi acilmamali; DISARM sonrasi
   **`SON UCUS OZETI` butonu aktiflesmeli** (pencere kendiliginden acilmaz).
4. Ucus Plani sekmesinde haritaya tiklayarak waypoint ekleyin, gorevi yukleyin.
5. Isterseniz **Baglanti Ayarlari** ile seri port (`PORT,BAUD`) kullanin.

## Paketlenmis surum (cift tiklama)

PyInstaller spec dosyasi QtWebEngine kaynaklarini (`icu`, `.pak` vb.) ve matplotlib Qt5Agg backend'ini toplar.

```bash
python3 -m pip install -r requirements.txt
pyinstaller --noconfirm --clean gcs.spec
```

Cikti:

- Linux: `dist/GCS`
- Windows: `dist/GCS.exe`

Calistirma:

```bash
./dist/GCS          # Linux
dist\GCS.exe        # Windows
```

Paket, `logs/` klasorunu **calistirilabilir dosyanin yaninda** olusturur (CSV ucus kayitlari oraya yazilir).

QtWebEngine bazi Linux kurulumlarinda sandbox izni ister; paket icinde `QTWEBENGINE_DISABLE_SANDBOX=1` otomatik ayarlanir. Harita Leaflet icin internet (unpkg CDN) gerekir.

Tek dosya paketleme QtWebEngine ile sorun cikarirsa ayni spec'teki `EXE` blogunu `exclude_binaries=True` + `COLLECT` (onedir) yapisina cevirmek gerekebilir.
