# GCS v7 — Yer Kontrol Istasyonu

PyQt5 + MAVLink tabanli otonom ucus yer istasyonu. Ana giris: `main_v7.py`.

## Gelistirme kurulumu

Python 3.8+ onerilir.

```bash
python3 -m pip install -r requirements.txt
python3 main_v7.py
```

Ilk calistirmada `logs/` klasoru (ucus CSV kayitlari) otomatik olusur.

## SITL ile test

ArduCopter SITL ornegi (ayri bir terminalde):

```bash
sim_vehicle.py -v ArduCopter --map --console
```

GCS varsayilan UDP adresi: `udp:127.0.0.1:14550`

1. GCS'i acin, baglanti rozetinin **BAGLI** oldugunu kontrol edin.
2. **Ucus Oncesi Kontrol Listesi** ile GPS/EKF/PreArm durumuna bakin.
3. ARM onayindan sonra ozet penceresi **acilmamali**; DISARM sonrasi acilmali.
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
