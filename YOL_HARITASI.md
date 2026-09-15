# GCS v7 — Gelistirme Yol Haritasi

Bu belge, uzerinde anlasilan 6 ozelligin sirasini, teknik temelini ve her
adimin "bitti" sayilma kosulunu tanimlar. Sira bilincli secilmistir:
paketleme (6) en sona birakilmistir, cunku her kod degisikliginden sonra
paketlemeyi tekrarlamak gerekir.

Durum isaretleri: `[ ]` yapilacak · `[~]` devam ediyor · `[x]` bitti

---

## 1. Son Ucus Ozeti Butonu `[x]`

### Sorun
Ozet penceresi DISARM aninda kendiliginden aciliyor. RTL/LAND gibi
surecler sirasinda otopilot kisa sureli, gercek olmayan bir DISARM
gorunumu uretebiliyor; bu da pencerenin pilotun onune beklenmedik bir
anda gelmesine sebep oluyor.

### Cozum
Pencere otomatik acilmaz. Ucus bittiginde ozet **saklanir** ve kontrol
panelindeki `SON UCUS OZETI` butonu aktiflesir; pilot hazir oldugunda
tiklar.

### Dokunulacak yerler
- `main_v7.py` → `MainWindow.__init__` (yeni `_last_flight_summary` alani)
- `main_v7.py` → `_build_telemetry_tab` (yeni buton, baslangicta pasif)
- `main_v7.py` → `_show_flight_summary` ikiye ayrilir:
  `_capture_flight_summary()` (saklar) + `on_last_summary_clicked()` (acar)
- `main_v7.py` → HEARTBEAT DISARM dali artik yakalama cagirir
- `ui/flight_summary_dialog.py` → docstring guncellemesi

### Kabul kriteri
- DISARM aninda pencere ACILMAZ.
- Buton ucus suresini de gosterecek sekilde aktiflesir (`SON UCUS OZETI (01:50)`).
- Butona basinca ozet penceresi eski icerikle acilir.
- Ucus yokken buton pasiftir.

### Test
`tests/test_flight_summary.py` — sahte arac ARM → DISARM yaptirilir;
pencerenin acilmadigi, butonun aktiflestigi ve saklanan ozetin dogru
oldugu dogrulanir.

---

## 2. Kalibrasyon Sihirbazlari `[x]`

### Amac
Pusula (compass/mag) ve ivmeolcer (accel) kalibrasyonu su an yalnizca
Mission Planner gibi harici bir yazilimla yapilabiliyor. Surec kendi
arayuzumuzden adim adim yonetilecek.

### MAVLink temeli
**Pusula:**
- Baslat: `MAV_CMD_DO_START_MAG_CAL` (42424) — param1=0 (tum pusulalar),
  param3=1 (autosave)
- Ilerleme: `MAG_CAL_PROGRESS` → `completion_pct`, `cal_status`
- Sonuc: `MAG_CAL_REPORT` → `cal_status`, `fitness`, `autosaved`
- Kabul: `MAV_CMD_DO_ACCEPT_MAG_CAL` (42425)
- Iptal: `MAV_CMD_DO_CANCEL_MAG_CAL` (42426)
- `MAG_CAL_STATUS`: 0 NOT_STARTED · 1 WAITING · 2 RUNNING_STEP_ONE ·
  3 RUNNING_STEP_TWO · 4 SUCCESS · 5 FAILED · 6 BAD_ORIENTATION · 7 BAD_RADIUS

**Ivmeolcer (6 pozisyonlu):**
- Baslat: `MAV_CMD_PREFLIGHT_CALIBRATION` (241), param5=1
- FC her adimda `STATUSTEXT` ile pozisyon ister ("Place vehicle level...")
- GCS yanit verir: `MAV_CMD_ACCELCAL_VEHICLE_POS` (42429), param1 =
  1 LEVEL · 2 LEFT · 3 RIGHT · 4 NOSEDOWN · 5 NOSEUP · 6 BACK

**Ek:** yatay duzlem (`param5=2`), jiroskop (`param1=1`), barometre (`param3=1`).

### Dokunulacak yerler
- `core/drone_telemetry.py` → `start_mag_cal`, `cancel_mag_cal`,
  `accept_mag_cal`, `start_accel_cal`, `send_accel_cal_position`,
  `start_simple_calibration`; `_decode`'a `MAG_CAL_PROGRESS` ve
  `MAG_CAL_REPORT` eklenir
- `main_v7.py` → `TelemetryWorker` komutlari; `MainWindow` sinyal baglantilari
- `ui/calibration_dialog.py` → **yeni**: sekmeli sihirbaz (Pusula / Ivmeolcer / Diger)

### Guvenlik kurali
Kalibrasyon yalnizca **DISARM** haldeyken baslatilabilir; ARM iken buton
pasif ve uyari gosterilir.

### Kabul kriteri
- Pusula sihirbazi ilerleme yuzdesini canli gosterir, iptal/kabul calisir.
- Ivmeolcer sihirbazi 6 pozisyonu sirayla ister, "Bu pozisyondayim"
  butonu FC'ye dogru pozisyon kodunu gonderir.
- ARM haldeyken kalibrasyon baslatilamaz.

### Test
`tests/test_calibration.py` — sahte arac gonderilen komutlari kaydeder;
dogru komut kimlikleri/parametreleri ve `MAG_CAL_PROGRESS` cozumlemesi
dogrulanir.

---

## 3. KML / .waypoints Disa Aktarma `[x]`

### Amac
Gorevler ve ucus kayitlari endustri standardi formatlara cevrilecek:
`.waypoints` (Mission Planner ve diger GCS'ler okur), `.kml` (Google
Earth'te 3 boyutlu goruntuleme).

### Format temeli
**QGC WPL 110** (`.waypoints`) — sekmeyle ayrilmis:
```
QGC WPL 110
0	1	0	16	0	0	0	0	<home_lat>	<home_lon>	0	1
1	0	3	16	0	0	0	0	<lat>	<lon>	<alt>	1
```
Satir 0 home'dur (frame 0). Gercek waypointler frame 3
(`GLOBAL_RELATIVE_ALT`), komut 16 (`NAV_WAYPOINT`), autocontinue 1.

**KML** — `<LineString>` + `altitudeMode=relativeToGround` + `<extrude>1`,
koordinat sirasi `boylam,enlem,irtifa`.

### Dokunulacak yerler
- `core/exporters.py` → **yeni**: `mission_to_waypoints()`,
  `mission_to_kml()`, `flight_log_to_kml()` (CSV ucus kaydindan)
- `ui/mission_panel.py` → "Disa Aktar" butonu (.waypoints / .kml)
- `ui/replay_panel.py` → secili CSV kaydi icin "KML'e Aktar" butonu

### Kabul kriteri
- Uretilen `.waypoints` dosyasi Mission Planner'in bekledigi satir
  duzenine birebir uyar (home satiri dahil).
- Uretilen `.kml` gecerli XML'dir ve Google Earth'te rota cizer.
- Bos gorev/kayit durumunda kullaniciya anlasilir uyari verilir.

### Test
`tests/test_exporters.py` — uretilen metin satir satir dogrulanir; KML
`xml.etree` ile ayristirilarak gecerliligi ve koordinat sirasi kontrol edilir.

---

## 4. Sesli Uyari Sistemi (TTS) `[x]`

### Amac
Kritik durumlar (dusuk pil, geofence ihlali, baglanti kaybi) su an sadece
ekranda yazi olarak gorunuyor. Pilot ekrana bakmiyorsa kaciriyor.

### Teknik yaklasim
Isletim sistemine gomulu TTS kullanilir, ek bagimlilik gerekmez:
- macOS: `say`
- Linux: `spd-say`, yoksa `espeak-ng` / `espeak`
- Windows: PowerShell `System.Speech.Synthesis.SpeechSynthesizer`

Konusma **ayri bir thread + kuyruk** uzerinden yapilir; GUI hicbir kosulda
bloklanmaz. Ayni uyari arka arkaya tekrarlanmaz (her mesaj turu icin
bekleme suresi).

### Tetiklenecek olaylar
| Olay | Ornek anons |
|---|---|
| Pil <= %20 | "Dusuk pil, yuzde on bes" |
| Geofence ihlali | "Geofence ihlali" |
| Baglanti kaybi / geri gelmesi | "Telemetri baglantisi kesildi" |
| ARM / DISARM | "Motorlar armed" |
| Kritik STATUSTEXT (severity <= 3) | mesajin kendisi |

### Dokunulacak yerler
- `core/voice_alerts.py` → **yeni**: `VoiceAlerts` sinifi (kuyruk + thread + throttle)
- `main_v7.py` → tetikleme noktalari ve durum cubugunda `SES: ACIK/KAPALI` butonu

### Kabul kriteri
- Ses kapatilabilir; kapaliyken hicbir alt surec baslatilmaz.
- TTS bulunmayan sistemde uygulama hatasiz calismaya devam eder.
- Ayni uyari bekleme suresi dolmadan tekrarlanmaz.

### Test
`tests/test_voice_alerts.py` — sahte konusma arka ucu ile kuyruk sirasi,
throttle ve kapali durumda hic cagri yapilmadigi dogrulanir.

---

## 5. Sinyal Kalitesi Gostergesi (RSSI) `[x]` — dusuk oncelik

### Amac
Telemetri radyosunun sinyal gucunu gostermek.

### MAVLink temeli
`RADIO_STATUS`: `rssi`, `remrssi` (0-255), `noise`, `remnoise`, `rxerrors`,
`fixed`. Yuzde karsiligi `rssi / 255 * 100`. SITL bu mesaji uretmez, bu
yuzden veri yokken gosterge `--` kalmalidir.

### Dokunulacak yerler
- `core/drone_telemetry.py` → `_TELEMETRY_TYPES` + `_decode`
- `main_v7.py` → yeni `StatCard` (SINYAL) ve renk esikleri
  (kirmizi <%30, sari <%60, yesil >=%60)

### Kabul kriteri
- `RADIO_STATUS` gelmiyorsa kart `--` gosterir, hata vermez.
- Geldiginde yuzde ve renk dogru guncellenir.

---

## 6. PyInstaller ile Paketleme `[x]` — en son

### Amac
Cift tiklamayla acilan tek dosya (Windows `.exe`, Linux/macOS
calistirilabilir). Python kurulu olmayan bilgisayarda ve sunumda calismali.

### Dikkat edilecekler
- QtWebEngine kaynaklari (`icu`, `.pak`) ve matplotlib Qt5Agg backend'i
  spec'te toplanmali (mevcut `gcs.spec` bunu yapiyor).
- **Yeni eklenen moduller** (`ui/calibration_dialog.py`,
  `core/exporters.py`, `core/voice_alerts.py`) `hiddenimports`a eklenmeli.
- `logs/` klasoru calistirilabilir dosyanin yaninda olusur
  (`core/app_paths.py` bunu zaten hallediyor).
- Harita Leaflet icin internet gerekir (unpkg CDN).

### Paketlemede cikan ve duzeltilen sorunlar

**1. Acilista 30+ saniye donma (matplotlib font onbellegi).**
Ilk paket denemesinde uygulama aciliyor ama arayuz gelmiyordu. Konsollu
bir tani paketi sorunu gosterdi: `ui/replay_panel.py` modul duzeyinde
`FlightGraphDialog` -> `matplotlib` yukluyordu; matplotlib de acilista
font taramasi yapiyor ve macOS'ta bunun icin `system_profiler` calistirdigi
icin onlarca saniye suruyordu. Ustelik tek dosya pakette matplotlib'in
yapilandirma dizini her calistirmada silinen gecici klasore dustugu icin
bu tarama HER ACILISTA tekrarlaniyordu.

Cozum:
- `FlightGraphDialog` importu grafik penceresi acilirken yapiliyor
  (modul duzeyinden cikarildi) — matplotlib artik acilis yolunda degil.
- Paketlenmis surumde `MPLCONFIGDIR` calistirilabilir dosyanin yanindaki
  kalici `.mpl-cache` klasorune ayarlaniyor.

Sonuc: `main_v7` import suresi 0.39 saniye.

**2. QtWebEngine bayragi.** `QApplication` olusturulmadan once
`Qt.AA_ShareOpenGLContexts` acikca ayarlaniyor. Gelistirmede
`ui.map_widget_v3` importu bunu tesadufen sagliyordu; paketlenmis surumde
import sirasina guvenmemek gerekir.

### Kabul kriteri
- `pyinstaller --noconfirm --clean gcs.spec` hatasiz tamamlanir.
- Uretilen dosya calistirilinca arayuz acilir ve SITL'e baglanir.
- Acilis birkac saniyede tamamlanir (donma yok).

---

## Her adimda uyulacak kurallar

1. **MAVLink kurali:** `self.master` soketine yalnizca `TelemetryWorker`
   thread'i dokunur. GUI komutlari `command_queue` uzerinden gider.
2. Her ozellik icin `tests/` altina test yazilir; testler gercek bir ucus
   kontrolcusu veya SITL gerektirmez (`FakeVehicle` kullanilir).
3. Her adim sonunda tum test takimi kosturulur:
   `python -m unittest discover -s tests`
4. Yeni dosyalar `gcs.spec` icindeki `hiddenimports` listesine eklenir
   (6. adimda toplu kontrol edilir).

---

## Sonra Konusulacak (kapsam disinda, karar verilmedi)

### 7. SQLite ucus gecmisi veritabani `[?]`
Su anda proje veritabani KULLANMIYOR ve mevcut kapsam icin buna gerek yok:
ucus kayitlari CSV (`logs/`), ayarlar ise ucus kontrolcusunun kendi
hafizasinda tutuluyor.

Gerekli hale gelecegi durumlar:
- Yuzlerce ucus arasinda arama / filtreleme
- Ucuslar arasi istatistik panosu (toplam ucus suresi, ortalama pil tuketimi)
- Coklu drone / filo yonetimi

Eklenirse: SQLite (tek dosya, kurulum gerektirmez), CSV kaydi **aynen
korunur** — veritabani CSV'nin yerine degil, uzerine bir indeks katmani
olarak gelir. Karar 1-6 bittikten sonra verilecek.
