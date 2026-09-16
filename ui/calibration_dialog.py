"""
calibration_dialog.py
----------------------
Pusula (compass) ve ivmeolcer (accelerometer) kalibrasyon sihirbazi.

Bu pencere MAVLink'e DOGRUDAN DOKUNMAZ: butonlar sinyal yayinlar,
MainWindow bunlari TelemetryWorker'in komut kuyruguna aktarir. FC'den
gelen MAG_CAL_PROGRESS / MAG_CAL_REPORT / STATUSTEXT mesajlari da yine
MainWindow uzerinden buraya iletilir.

Guvenlik: kalibrasyon yalnizca DISARM haldeyken baslatilabilir.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.drone_telemetry import (
    ACCEL_CAL_POS_FAILED,
    ACCEL_CAL_POS_SUCCESS,
    ACCEL_CAL_STEPS,
    MAG_CAL_STATUS_TEXTS,
)

# FC'nin ivmeolcer adimlarinda gonderdigi STATUSTEXT'ten pozisyonu cikarmak
# icin YEDEK esleme.
#
# ASIL kanal COMMAND_LONG / MAV_CMD_ACCELCAL_VEHICLE_POS'tur
# (on_accel_position_request). ArduPilot kaynagi (AP_AccelCal.cpp)
# gcs_vehicle_position() icinde ilk yanitimizda _use_gcs_snoop'u kapatir,
# yani "Place vehicle ..." metinleri SADECE ilk adimda gelir. Bu esleme
# eski/snoop davranisi ve ilk adim icin korunur.
#
# Sira onemli: "nose down" / "nose up" daha genel anahtarlardan once gelir.
_POS_KEYWORDS = (
    ("nose down", 4),
    ("nosedown", 4),
    ("nose up", 5),
    ("noseup", 5),
    ("left", 2),
    ("right", 3),
    ("back", 6),
    ("level", 1),
)

_BASARI_ANAHTARLARI = ("calibration successful", "calibration success")
_HATA_ANAHTARLARI = ("calibration failed", "calibration cancelled")


def pozisyon_kodu_bul(text: str):
    """STATUSTEXT bir pozisyon istegi ise (1..6) kodunu, degilse None doner."""
    low = (text or "").lower()
    if "place" not in low and "vehicle" not in low:
        return None
    for anahtar, kod in _POS_KEYWORDS:
        if anahtar in low:
            return kod
    return None


class _Adim(QFrame):
    """Ivmeolcer sihirbazinda tek bir pozisyon satiri."""

    def __init__(self, sira: int, baslik: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        self._numara = QLabel(str(sira))
        self._numara.setFixedWidth(22)
        self._baslik = QLabel(baslik)
        layout.addWidget(self._numara)
        layout.addWidget(self._baslik, 1)
        self.durum_ayarla("bekliyor")

    def durum_ayarla(self, durum: str):
        renkler = {
            "bekliyor": ("#6c7086", "#181825"),
            "aktif": ("#f9e2af", "#313244"),
            "bitti": ("#a6e3a1", "#181825"),
        }
        renk, arka = renkler.get(durum, renkler["bekliyor"])
        self.setStyleSheet(
            f"background-color: {arka}; border: 1px solid #313244; border-radius: 8px;"
        )
        self._numara.setStyleSheet(f"color: {renk}; font-weight: 800; background: transparent;")
        isaret = {"bekliyor": "", "aktif": "  ←", "bitti": "  ✓"}[durum]
        metin = self._baslik.text().split("  ")[0]
        self._baslik.setText(f"{metin}{isaret}")
        self._baslik.setStyleSheet(f"color: {renk}; font-weight: 700; background: transparent;")


class CalibrationDialog(QDialog):
    start_mag_requested = pyqtSignal()
    accept_mag_requested = pyqtSignal()
    cancel_mag_requested = pyqtSignal()
    start_accel_requested = pyqtSignal()
    accel_position_confirmed = pyqtSignal(int)
    start_level_requested = pyqtSignal()
    start_gyro_requested = pyqtSignal()
    start_baro_requested = pyqtSignal()

    def __init__(self, armed: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kalibrasyon Sihirbazi")
        self.setMinimumWidth(520)
        self.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4;")

        self._armed = armed
        self._mag_calisiyor = False
        self._accel_calisiyor = False
        self._accel_adim = 0

        root = QVBoxLayout(self)

        self.lbl_uyari = QLabel()
        self.lbl_uyari.setWordWrap(True)
        self.lbl_uyari.setStyleSheet(
            "background-color: #45262f; color: #f38ba8; border-radius: 8px; "
            "padding: 8px; font-weight: 700;"
        )
        root.addWidget(self.lbl_uyari)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._pusula_sekmesi(), "Pusula")
        self.tabs.addTab(self._ivmeolcer_sekmesi(), "Ivmeolcer")
        self.tabs.addTab(self._diger_sekmesi(), "Diger")
        root.addWidget(self.tabs)

        kayit_grup = QGroupBox("Otopilot Mesajlari")
        kayit_layout = QVBoxLayout()
        self.liste_mesaj = QListWidget()
        self.liste_mesaj.setMaximumHeight(110)
        self.liste_mesaj.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; border-radius: 8px;"
        )
        kayit_layout.addWidget(self.liste_mesaj)
        kayit_grup.setLayout(kayit_layout)
        root.addWidget(kayit_grup)

        kapat = QPushButton("Kapat")
        kapat.clicked.connect(self.close)
        root.addWidget(kapat)

        self.set_armed(armed)

    # ---------------- sekmeler ----------------

    def _pusula_sekmesi(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        aciklama = QLabel(
            "Kalibrasyon baslayinca araci HER EKSENDE yavasca cevirin "
            "(burun yukari/asagi, saga/sola yatirin, kendi ekseninde dondurun). "
            "Yuzde 100'e ulasinca sonuc raporlanir.\n\n"
            "Sonuc, siz 'Kabul Et' demeden otopilota KAYDEDILMEZ."
        )
        aciklama.setWordWrap(True)
        aciklama.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(aciklama)

        self.mag_progress = QProgressBar()
        self.mag_progress.setRange(0, 100)
        self.mag_progress.setValue(0)
        self.mag_progress.setStyleSheet(
            "QProgressBar { background-color: #181825; border: 1px solid #313244; "
            "border-radius: 8px; height: 22px; text-align: center; color: #cdd6f4; } "
            "QProgressBar::chunk { background-color: #89b4fa; border-radius: 7px; }"
        )
        layout.addWidget(self.mag_progress)

        self.lbl_mag_durum = QLabel("Durum: baslatilmadi")
        self.lbl_mag_durum.setWordWrap(True)
        self.lbl_mag_durum.setStyleSheet("color: #cdd6f4; font-weight: 700;")
        layout.addWidget(self.lbl_mag_durum)

        satir = QHBoxLayout()
        self.btn_mag_start = QPushButton("PUSULA KALIBRASYONUNU BASLAT")
        self.btn_mag_start.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; "
            "padding: 10px; border-radius: 8px;"
        )
        self.btn_mag_start.clicked.connect(self._mag_baslat)
        self.btn_mag_cancel = QPushButton("Iptal")
        self.btn_mag_cancel.setEnabled(False)
        self.btn_mag_cancel.clicked.connect(self._mag_iptal)
        satir.addWidget(self.btn_mag_start, 1)
        satir.addWidget(self.btn_mag_cancel)
        layout.addLayout(satir)

        self.btn_mag_accept = QPushButton("KABUL ET VE KAYDET")
        self.btn_mag_accept.setEnabled(False)
        self.btn_mag_accept.setStyleSheet(
            "background-color: #313244; color: #6c7086; font-weight: 800; "
            "padding: 10px; border-radius: 8px;"
        )
        self.btn_mag_accept.clicked.connect(self._mag_kabul)
        layout.addWidget(self.btn_mag_accept)
        layout.addStretch()
        return w

    def _ivmeolcer_sekmesi(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        aciklama = QLabel(
            "Arac 6 farkli pozisyona getirilir. Her pozisyonda araci "
            "SABIT tutun ve 'BU POZISYONDAYIM' butonuna basin."
        )
        aciklama.setWordWrap(True)
        aciklama.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(aciklama)

        self._adim_satirlari = []
        adim_kutu = QGridLayout()
        for i, (_kod, baslik, _tarif) in enumerate(ACCEL_CAL_STEPS):
            satir = _Adim(i + 1, baslik)
            self._adim_satirlari.append(satir)
            adim_kutu.addWidget(satir, i // 2, i % 2)
        layout.addLayout(adim_kutu)

        self.lbl_accel_talimat = QLabel("Baslatmak icin asagidaki butona basin.")
        self.lbl_accel_talimat.setWordWrap(True)
        self.lbl_accel_talimat.setAlignment(Qt.AlignCenter)
        self.lbl_accel_talimat.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; border-radius: 10px; "
            "padding: 14px; color: #f9e2af; font-size: 15px; font-weight: 800;"
        )
        layout.addWidget(self.lbl_accel_talimat)

        self.btn_accel_start = QPushButton("IVMEOLCER KALIBRASYONUNU BASLAT")
        self.btn_accel_start.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; "
            "padding: 10px; border-radius: 8px;"
        )
        self.btn_accel_start.clicked.connect(self._accel_baslat)
        layout.addWidget(self.btn_accel_start)

        self.btn_accel_next = QPushButton("BU POZISYONDAYIM → DEVAM")
        self.btn_accel_next.setEnabled(False)
        self.btn_accel_next.setStyleSheet(
            "background-color: #313244; color: #6c7086; font-weight: 800; "
            "padding: 12px; border-radius: 8px;"
        )
        self.btn_accel_next.clicked.connect(self._accel_devam)
        layout.addWidget(self.btn_accel_next)
        layout.addStretch()
        return w

    def _diger_sekmesi(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        tanimlar = [
            ("YATAY DUZLEM (LEVEL)", "Araci duz zemine koyup calistirin; "
             "ufuk gostergesinin sifirini duzeltir.", self.start_level_requested),
            ("JIROSKOP", "Arac tamamen HAREKETSIZ olmali.", self.start_gyro_requested),
            ("BAROMETRE (YER BASINCI)", "Irtifa sifirini bulundugunuz "
             "yukseklige gore yeniden ayarlar.", self.start_baro_requested),
        ]
        self._diger_butonlar = []
        for baslik, aciklama, sinyal in tanimlar:
            kutu = QGroupBox(baslik)
            kl = QVBoxLayout()
            lbl = QLabel(aciklama)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
            kl.addWidget(lbl)
            btn = QPushButton("BASLAT")
            btn.clicked.connect(lambda _c=False, s=sinyal, b=baslik: self._diger_baslat(s, b))
            kl.addWidget(btn)
            kutu.setLayout(kl)
            layout.addWidget(kutu)
            self._diger_butonlar.append(btn)
        layout.addStretch()
        return w

    # ---------------- guvenlik ----------------

    def set_armed(self, armed: bool):
        """ARM haldeyken hicbir kalibrasyon baslatilamaz."""
        self._armed = bool(armed)
        if self._armed:
            self.lbl_uyari.setText(
                "ARAC ARM DURUMDA — kalibrasyon baslatilamaz. Once DISARM edin."
            )
            self.lbl_uyari.show()
        else:
            self.lbl_uyari.hide()
        for btn in [self.btn_mag_start, self.btn_accel_start] + self._diger_butonlar:
            btn.setEnabled(not self._armed)

    # ---------------- pusula ----------------

    def _mag_baslat(self):
        if self._armed:
            return
        self._mag_calisiyor = True
        self.mag_progress.setValue(0)
        self.lbl_mag_durum.setText("Durum: baslatiliyor...")
        self.btn_mag_start.setEnabled(False)
        self.btn_mag_cancel.setEnabled(True)
        self._accept_butonu_ayarla(False)
        self.start_mag_requested.emit()

    def _mag_iptal(self):
        self.cancel_mag_requested.emit()
        self._mag_bitir("Durum: iptal edildi")

    def _mag_kabul(self):
        self.accept_mag_requested.emit()
        self.lbl_mag_durum.setText("Durum: kalibrasyon kaydedildi")
        self._accept_butonu_ayarla(False)

    def _accept_butonu_ayarla(self, aktif: bool):
        self.btn_mag_accept.setEnabled(aktif)
        if aktif:
            self.btn_mag_accept.setStyleSheet(
                "background-color: #a6e3a1; color: #1e1e2e; font-weight: 800; "
                "padding: 10px; border-radius: 8px;"
            )
        else:
            self.btn_mag_accept.setStyleSheet(
                "background-color: #313244; color: #6c7086; font-weight: 800; "
                "padding: 10px; border-radius: 8px;"
            )

    def _mag_bitir(self, durum_metni):
        self._mag_calisiyor = False
        self.btn_mag_start.setEnabled(not self._armed)
        self.btn_mag_cancel.setEnabled(False)
        self.lbl_mag_durum.setText(durum_metni)

    def on_mag_progress(self, data: dict):
        """FC'den gelen MAG_CAL_PROGRESS."""
        pct = int(data.get("completion_pct", 0))
        durum = int(data.get("cal_status", 0))
        self.mag_progress.setValue(max(0, min(100, pct)))
        self.lbl_mag_durum.setText(
            f"Durum: {MAG_CAL_STATUS_TEXTS.get(durum, durum)} — %{pct}"
        )

    def on_mag_report(self, data: dict):
        """FC'den gelen MAG_CAL_REPORT: kalibrasyonun sonucu."""
        durum = int(data.get("cal_status", 0))
        fitness = data.get("fitness")
        metin = MAG_CAL_STATUS_TEXTS.get(durum, str(durum))
        basarili = durum == 4
        if basarili:
            self.mag_progress.setValue(100)
            self._mag_bitir(
                f"Durum: {metin} (uyum: {fitness:.2f}) — kaydetmek icin 'KABUL ET'"
            )
            self._accept_butonu_ayarla(True)
        else:
            self._mag_bitir(f"Durum: {metin}")
            self._accept_butonu_ayarla(False)

    # ---------------- ivmeolcer ----------------

    def _accel_baslat(self):
        if self._armed:
            return
        self._accel_calisiyor = True
        self._accel_adim = 0
        for satir in self._adim_satirlari:
            satir.durum_ayarla("bekliyor")
        self._adim_goster(0)
        self.btn_accel_start.setEnabled(False)
        self.btn_accel_next.setEnabled(True)
        self.btn_accel_next.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: 800; "
            "padding: 12px; border-radius: 8px;"
        )
        self.start_accel_requested.emit()

    def _adim_goster(self, index: int):
        if index >= len(ACCEL_CAL_STEPS):
            return
        for i, satir in enumerate(self._adim_satirlari):
            if i < index:
                satir.durum_ayarla("bitti")
            elif i == index:
                satir.durum_ayarla("aktif")
            else:
                satir.durum_ayarla("bekliyor")
        _kod, baslik, tarif = ACCEL_CAL_STEPS[index]
        self.lbl_accel_talimat.setText(f"{index + 1}/6 — {baslik}\n{tarif}")

    def _accel_devam(self):
        if not self._accel_calisiyor:
            return
        kod = ACCEL_CAL_STEPS[self._accel_adim][0]
        self.accel_position_confirmed.emit(kod)
        self._adim_satirlari[self._accel_adim].durum_ayarla("bitti")
        self._accel_adim += 1
        if self._accel_adim >= len(ACCEL_CAL_STEPS):
            self.btn_accel_next.setEnabled(False)
            self.lbl_accel_talimat.setText("Tum pozisyonlar gonderildi, sonuc bekleniyor...")
        else:
            self._adim_goster(self._accel_adim)

    def on_accel_position_request(self, data: dict):
        """FC'nin pozisyon istegi (ASIL kanal); param1 = pozisyon (1..6)
        veya sonuc kodu."""
        if not self._accel_calisiyor:
            return
        pozisyon = int(data.get("position", 0))

        if pozisyon == ACCEL_CAL_POS_SUCCESS:
            self._accel_bitir("Ivmeolcer kalibrasyonu BASARILI", True)
            return
        if pozisyon == ACCEL_CAL_POS_FAILED:
            self._accel_bitir(
                "Ivmeolcer kalibrasyonu BASARISIZ — araci istenen pozisyonda "
                "sabit tutup tekrar deneyin",
                False,
            )
            return

        for i, (kod, _b, _t) in enumerate(ACCEL_CAL_STEPS):
            if kod == pozisyon and i != self._accel_adim:
                self._accel_adim = i
                self._adim_goster(i)
                self.btn_accel_next.setEnabled(True)
                self.mesaj_ekle(f"FC {i + 1}. pozisyonu istiyor")
                break

    def _accel_bitir(self, metin: str, basarili: bool):
        self._accel_calisiyor = False
        self.btn_accel_start.setEnabled(not self._armed)
        self.btn_accel_next.setEnabled(False)
        self.btn_accel_next.setStyleSheet(
            "background-color: #313244; color: #6c7086; font-weight: 800; "
            "padding: 12px; border-radius: 8px;"
        )
        if basarili:
            for satir in self._adim_satirlari:
                satir.durum_ayarla("bitti")
        self.lbl_accel_talimat.setText(metin)

    # ---------------- diger ----------------

    def _diger_baslat(self, sinyal, baslik):
        if self._armed:
            return
        sinyal.emit()
        self.mesaj_ekle(f"{baslik} kalibrasyonu baslatildi")

    # ---------------- FC mesajlari ----------------

    def mesaj_ekle(self, metin: str):
        self.liste_mesaj.addItem(metin)
        self.liste_mesaj.scrollToBottom()

    def on_statustext(self, data: dict):
        """FC'den gelen STATUSTEXT. Ivmeolcer kalibrasyonunda pozisyon
        istekleri ve sonuc bildirimi bu kanaldan gelir."""
        metin = (data.get("text") or "").strip()
        if not metin:
            return
        low = metin.lower()
        ilgili = self._accel_calisiyor or self._mag_calisiyor or "cal" in low
        if ilgili:
            self.mesaj_ekle(metin)

        if not self._accel_calisiyor:
            return

        if any(a in low for a in _BASARI_ANAHTARLARI):
            self._accel_bitir("Ivmeolcer kalibrasyonu BASARILI", True)
            return
        if any(a in low for a in _HATA_ANAHTARLARI):
            self._accel_bitir(f"Ivmeolcer kalibrasyonu BASARISIZ: {metin}", False)
            return

        kod = pozisyon_kodu_bul(metin)
        if kod is not None:
            # FC'nin istedigi pozisyon ile sihirbazin adimini senkronla
            # (orn. FC bir pozisyonu tekrar isterse geri adim atariz).
            for i, (adim_kodu, _b, _t) in enumerate(ACCEL_CAL_STEPS):
                if adim_kodu == kod:
                    self._accel_adim = i
                    self._adim_goster(i)
                    self.btn_accel_next.setEnabled(True)
                    break
