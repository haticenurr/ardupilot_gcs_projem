# Test ve Kullanim Rehberi

Bu belge GCS'i acmanin ve tum ozellikleri denemenin uc yolunu anlatir.
En hizlisi **Yol A**'dir: ArduPilot SITL kurmadan, sahte bir drone ile
arayuzun tamamini canli veriyle test edebilirsiniz.

---

## 0. Bir kereye mahsus hazirlik

```bash
cd /Applications/projeler/proje
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Sonraki acilislarda sadece `source .venv/bin/activate` yeterlidir.

---

## Yol A — Sahte drone ile (SITL gerekmez, en hizli)

**Iki terminal** acin.

**Terminal 1 — sahte drone:**
```bash
cd /Applications/projeler/proje
.venv/bin/python tests/fake_vehicle.py
```

Bu terminalde klavye komutlari:

| Tus | Etki |
|---|---|
| `Enter` | ARM / DISARM (ucus baslat / bitir) |
| `b` | Dusuk pil (%15) bildirimi gonder |
| `f` | Geofence ihlali mesaji gonder |
| `r` | Telemetri radyosu sinyal raporu (RSSI) gonder |
| `q` | Cikis |

**Terminal 2 — yer istasyonu:**
```bash
cd /Applications/projeler/proje
.venv/bin/python main_v7.py
```

Ust cubuktaki rozet birkac saniye icinde **BAGLI** olmalidir.

> Sahte drone gercek bir otopilot degildir: gorev yukleme, kalibrasyon ve
> mod degistirme gibi otopilot tarafi gerektiren islemler yanit vermez.
> Onlari denemek icin **Yol B**'yi kullanin.

---

## Yol B — ArduPilot SITL ile (gercekci)

### Kurulum (bir kereye mahsus)

```bash
cd /Applications/projeler
git clone --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/ArduPilot/ardupilot.git

# Derleme araclari icin ayri bir sanal ortam
python3 -m venv ardupilot-venv
ardupilot-venv/bin/python -m pip install "empy==3.3.4" pexpect future pymavlink

cd ardupilot
../ardupilot-venv/bin/python ./waf configure --board sitl
../ardupilot-venv/bin/python ./waf copter
```

Sonuc: `ardupilot/build/sitl/bin/arducopter` (~5 MB). Derleme birkac dakika surer.

> **MAVProxy kurulmasina gerek yok.** `pip install MAVProxy`, Python 3.9'da
> hazir wheel'i olmayan `fastcrc` paketini Rust ile derlemeye calisir ve
> takilir. Asagidaki calistirma bicimi MAVProxy'siz calisir.

### Calistirma

**Terminal 1 — SITL:**
```bash
cd /Applications/projeler/ardupilot
./build/sitl/bin/arducopter --model quad \
    --serial0 tcp:5760 \
    --serial1 udpclient:127.0.0.1:14550 \
    --defaults Tools/autotest/default_params/copter.parm
```

Iki secenek de onemlidir:

| Secenek | Neden |
|---|---|
| `--serial0 tcp:5760` | `:wait` **eklenmez**. Varsayilan `tcp:5760:wait` oldugu icin SITL, 5760'a biri baglanana kadar bekler ve hicbir telemetri yayinlamaz. Ayrica her yeni TCP baglantisinda kendini sifirlar — bu, kalibrasyon gibi cok adimli islemleri yarida keser. |
| `--serial1 udpclient:127.0.0.1:14550` | Projenin varsayilan adresinde ayri ve kararli bir MAVLink akisi acar. |

**Terminal 2 — yer istasyonu:**
```bash
cd /Applications/projeler/proje
.venv/bin/python main_v7.py
```

SITL ile gorev yukleme, otonom ucus sihirbazi, kalibrasyon ve parametre
yazma islemlerinin tamami calisir.

### Protokol dogrulama betigi

SITL calisirken, gonderdigimiz komutlara gercek otopilotun verdigi yaniti
uctan uca kontrol eder:

```bash
.venv/bin/python tests/sitl_dogrula.py
```

Beklenen: **18/18 kontrol gecti**. Telemetri cozumlemesi, RTL irtifa
parametresi, gorev yukleme/indirme turu, ivmeolcer protokol akisi ve
pusula kalibrasyonu ilerleme mesajlari dogrulanir.

> **SITL siniri:** ivmeolcer kalibrasyonunun 6 pozisyonu SITL'de
> TAMAMLANAMAZ, cunku simulasyondaki arac fiziksel olarak cevrilemez.
> 2. pozisyonda ornek yanlis olur ve FC `Calibration FAILED` bildirir.
> Bu bir hata degildir; betik de bunu boyle bekler. Dogrulanan sey
> protokol akisidir (FC pozisyon istiyor -> GCS yanitliyor -> FC bir
> sonrakini istiyor).

> SITL `RADIO_STATUS` mesaji **uretmez** — bu yuzden SINYAL karti `--`
> kalir. Bu bir hata degildir; gercek telemetri radyosunda dolar.
> RSSI'yi denemek icin Yol A'da `r` tusunu kullanin.

---

## Yol C — Paketlenmis surum (sunum / juri icin)

Python kurulu olmayan bilgisayarda da calisir:

```bash
open dist/GCS            # macOS
./dist/GCS               # Linux
dist\GCS.exe             # Windows
```

Paketi yeniden uretmek icin:
```bash
.venv/bin/pyinstaller --noconfirm --clean gcs.spec
```

> PyInstaller **caprazderleme yapmaz**: Windows `.exe` uretmek icin
> paketlemeyi bir Windows bilgisayarda calistirmaniz gerekir.
>
> Ilk acilis, matplotlib font onbellegi kuruldugu icin bir kez yavas
> olabilir; onbellek `dist/.mpl-cache` icine yazilir ve sonraki acilislar
> hizlidir.

---

## Otomatik testler

Gercek bir ucus kontrolcusu veya SITL gerektirmez, ~30 saniye surer:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Beklenen: **59 test, OK**. Test sirasinda bilgisayar konusmaz (sesli
uyarilar sahte bir arka uca yonlendirilir) ve `logs/` klasorune dosya
birakilmaz.

Tek bir bolumu calistirmak icin:
```bash
.venv/bin/python -m unittest tests.test_calibration -v
```

---

## Ozellik ozellik kontrol listesi

Asagidakiler **Yol A** ile denenebilir (aksi belirtilmedikce).

### 1. Son Ucus Ozeti

1. Sahte drone terminalinde `Enter` → ARM.
2. 10-15 saniye bekleyin.
3. `Enter` → DISARM.

**Beklenen:** ozet penceresi **kendiliginden ACILMAZ**. "Komuta ve
Kontrol" bolumundeki `SON UCUS OZETI` butonu mavi olur ve ucus suresini
gosterir (`SON UCUS OZETI (00:14)`). Butona basinca ozet acilir; tekrar
tekrar acilabilir.

**Neden boyle:** RTL/LAND sirasinda otopilot kisa sureli, gercek olmayan
bir DISARM gorunumu uretebiliyor ve pencere beklenmedik anda aciliyordu.

### 2. Kalibrasyon sihirbazi

Ust cubuk → **Kalibrasyon**. Uc sekme vardir: Pusula, Ivmeolcer, Diger.

- **ARM korumasi (Yol A ile denenebilir):** sihirbaz acikken `Enter` ile
  ARM edin. Kirmizi uyari cikmali ve tum baslatma butonlari pasiflesmeli.
  DISARM edince tekrar aktiflesmeli.
- **Pusula (Yol B gerekir):** `PUSULA KALIBRASYONUNU BASLAT` → araci her
  eksende cevirin, ilerleme cubugu dolar. Bitince `KABUL ET VE KAYDET`
  aktiflesir. **Kabul etmeden otopilota yazilmaz** (autosave kapali).
- **Ivmeolcer (Yol B gerekir):** 6 pozisyon sirayla istenir; her
  pozisyonda `BU POZISYONDAYIM → DEVAM`. Hangi pozisyonun istendigini
  otopilot bildirir (`MAV_CMD_ACCELCAL_VEHICLE_POS`), sihirbaz ona gore
  senkronlanir.

### 3. Disa aktarma

1. **Ucus Plani** sekmesine gecin, haritaya tiklayarak 3-4 waypoint ekleyin.
2. **Disa Aktar** butonuna basin.
3. `gorev.waypoints` olarak kaydedin → Mission Planner / QGroundControl
   ile acilabilir.
4. Tekrar deneyin, bu kez `gorev.kml` olarak kaydedin → Google Earth'te
   acin, rota 3 boyutlu gorunur.

Ucus kaydi icin: **Replay** panelinde bir CSV secin → **KML** butonu.

### 4. Sesli uyarilar

Ust cubukta `SES: ACIK` yazmali. (`SES: YOK` yaziyorsa sisteminizde metin
okuma araci bulunamamistir — uygulama yine calisir, sadece sessizdir.)

- Sahte drone terminalinde `b` → "Dusuk pil, yuzde 15" duyulmali.
- `f` → "Geofence ihlali" duyulmali.
- `Enter` → "Motorlar armed" / "Motorlar disarmed".

Ayni uyari arka arkaya tekrarlanmaz (dusuk pil icin 30 saniye bekleme).
Butona basarak sesi kapatabilirsiniz.

### 5. Sinyal gostergesi (RSSI)

Sahte drone terminalinde `r` → telemetri kartlarindaki **SINYAL** karti
yuzde degeri gosterir. Renk esikleri: kirmizi <%30, sari <%60, yesil >=%60.

### 6. Diger mevcut ozellikler

- **Ucus Oncesi Kontrol Listesi** (Komuta ve Kontrol)
- **Parametreler** (ust cubuk) — FC parametrelerini okuma/yazma
- **Guvenlik paneli** — PreArm, EKF, sensor sagligi, geofence
- **Replay** — kayitli CSV ucusunu haritada geri oynatma, grafik

---

## Sorun giderme

| Belirti | Sebep / cozum |
|---|---|
| Rozet **BEKLENIYOR**'da kaliyor | Sahte drone veya SITL calismiyor. Terminal 1'i kontrol edin. |
| `Address already in use` | 14550 portunu baska bir program tutuyor (eski bir GCS/SITL). O sureci kapatin. |
| Harita bos / gri | Leaflet ve harita doselemeleri internetten gelir (unpkg + CARTO). Internet baglantisini kontrol edin. |
| `SES: YOK` | Sistemde TTS araci yok. Linux'ta `sudo apt install espeak-ng` yeterlidir. |
| SINYAL karti `--` | SITL `RADIO_STATUS` uretmez. Normal. Yol A'da `r` ile test edin. |
| Paketlenmis surum ilk acilista yavas | matplotlib font onbellegi bir kez kuruluyor. Ikinci acilis hizlidir. |
| Testler `ModuleNotFoundError` veriyor | Sanal ortam etkin degil. `.venv/bin/python` ile calistirin. |
