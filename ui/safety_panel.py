"""
safety_panel.py
----------------
Pre-arm / guvenlik kontrol paneli.

Gosterdikleri:
  - Sensor sagligi (SYS_STATUS'tan): jiroskop, ivmeolcer, pusula, barometre,
    GPS, RC alici, AHRS, batarya monitoru -> yesil/kirmizi/gri nokta
  - EKF durumu (EKF_STATUS_REPORT'tan): konum/hiz tahmini guvenilir mi
  - Aktif PreArm uyarilari (STATUSTEXT'ten, "PreArm:" ile baslayan veya
    ERROR/CRITICAL seviyesindeki mesajlar). Bir mesaj bir sure tekrar
    gelmezse (cozulmus sayilir) listeden otomatik dusurulur.
  - Ust banner: ARM'A HAZIR / ARM'A HAZIR DEGIL / ARMED

Kullanim (MainWindow icinde):
    self.safety_panel = PrearmPanel()
    ...
    # update_telemetry_ui() icinde ilgili mesaj tiplerini yonlendir:
    if msg_type == "HEARTBEAT":
        self.safety_panel.set_armed(data["armed"])
    elif msg_type == "SYS_STATUS":
        self.safety_panel.process_sys_status(data)
    elif msg_type == "EKF_STATUS_REPORT":
        self.safety_panel.process_ekf_status(data)
    elif msg_type == "STATUSTEXT":
        self.safety_panel.process_statustext(data)

    # baglanti koptugunda / yeniden baglanmadan once:
    self.safety_panel.reset_connection_state()

    # periyodik olarak (orn. 1-2 sn'de bir, bir QTimer ile) eski PreArm
    # mesajlarinin listeden dusurulmesi icin:
    self.safety_panel.tick()
"""

import time

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# Bu sureden uzun suredir tekrarlanmayan PreArm mesaji "cozulmus" sayilir
# ve listeden dusurulur. ArduPilot disarmken hata devam ettigi surece
# PreArm mesajlarini birkac saniyede bir tekrar yayinlar; bu yuzden kisa
# bir sessizlik gercek cozulme anlamina gelir.
PREARM_STALE_S = 10.0
# Yaygin ArduPilot PreArm/hata metinlerini sade Turkce aciklamalarla
# eslestirir. Her giris (anahtar_kelimeler_tuple, aciklama) seklindedir;
# anahtar kelimelerin HEPSI (kucuk harfe cevrilmis) ham metinde geciyorsa
# eslesme sayilir. Eslesme bulunamazsa ham metin oldugu gibi gosterilir,
# ASLA gizlenmez. Yeni bir kalip eklemek icin listeye bir satir eklemek
# yeterli - kolay genisletilebilir olmasi icin bilincli olarak duz liste
# halinde tutuluyor.
PREARM_TRANSLATIONS = [
    (("ekf", "variance"), "GPS sinyali zayif veya pusula kalibre edilmemis. Acik alana cikin."),
    (("compass", "not calibrated"), "Pusula kalibre edilmemis. Kalibrasyonu tamamlayin."),
    (("compass", "variance"), "Pusula ile GPS yonu uyusmuyor. Metal nesnelerden uzaklasip tekrar deneyin."),
    (("gps", "bad fix"), "GPS sinyali zayif veya kilitlenmemis. Acik alanda GPS kilidini bekleyin."),
    (("gps", "hdop"), "GPS konum hassasiyeti dusuk. Acik alanda daha fazla uydu sinyali bekleyin."),
    (("need", "position", "estimate"), "Konum tahmini yok. GPS kilidini ve EKF durumunu kontrol edin."),
    (("rc", "not calibrated"), "Uzaktan kumanda kalibre edilmemis. RC kalibrasyonunu tamamlayin."),
    (("waiting", "rc"), "Uzaktan kumanda sinyali bekleniyor. Vericinin acik oldugundan emin olun."),
    (("battery",), "Batarya voltaji dusuk veya okunamiyor. Bataryayi kontrol edin."),
    (("ins", "not calibrated"), "IMU (jiroskop/ivmeolcer) kalibre edilmemis."),
    (("accel", "inconsistent"), "Ivmeolcer degerleri tutarsiz. IMU kalibrasyonunu tekrarlayin."),
    (("gyro", "inconsistent"), "Jiroskop degerleri tutarsiz. Araci sabit bir zeminde tutup tekrar deneyin."),
    (("throttle",), "Gaz kolu (throttle) sifir konumda degil. Kolu sifirlayin."),
    (("safety switch",), "Guvenlik anahtari basili degil. Anahtara basin."),
    (("barometer",), "Barometre (irtifa sensoru) sorunlu. Sensoru kontrol edin."),
    (("arming", "disabled"), "ARM islemi otopilot tarafindan devre disi birakilmis. Parametreleri kontrol edin."),
]


def translate_prearm_text(raw_text: str):
    """Ham PreArm/hata metnini sade bir Turkce aciklamayla eslestirmeye
    calisir. Eslesme bulunamazsa None doner (ham metin fallback olarak
    kullanilir, hicbir zaman gizlenmez)."""
    lower = raw_text.lower()
    for keywords, explanation in PREARM_TRANSLATIONS:
        if all(keyword in lower for keyword in keywords):
            return explanation
    return None

SENSOR_LABELS = {
    "gyro": "Jiroskop",
    "accel": "Ivmeolcer",
    "mag": "Pusula",
    "baro": "Barometre",
    "gps": "GPS",
    "rc": "RC Alici",
    "ahrs": "AHRS",
    "battery": "Batarya Monitoru",
}

# EKF_STATUS_REPORT.flags bitleri (EKF_STATUS_FLAGS enum'u):
#   1  EKF_ATTITUDE
#   2  EKF_VELOCITY_HORIZ
#   4  EKF_VELOCITY_VERT
#   8  EKF_POS_HORIZ_REL
#  16  EKF_POS_HORIZ_ABS
#  32  EKF_POS_VERT_ABS
#  64  EKF_POS_VERT_AGL
# 128  EKF_CONST_POS_MODE
# 256  EKF_PRED_POS_HORIZ_REL
# 512  EKF_PRED_POS_HORIZ_ABS
# Arm icin en kritik olanlar: attitude + hiz + yatay/dusey mutlak konum.
_EKF_REQUIRED_FLAGS = 1 | 2 | 16 | 32

# Her bitin ne anlama geldigi - EKF sorunlu ciktiginda kullaniciya HANGI
# kismin sorunlu oldugunu (sadece "sorunlu" degil, NEDEN sorunlu) gostermek icin.
_EKF_FLAG_LABELS = {
    1: "Yonelim tahmini",
    2: "Yatay hiz tahmini",
    4: "Dikey hiz tahmini",
    8: "Yatay konum (goreceli)",
    16: "Yatay konum (GPS/mutlak)",
    32: "Dikey konum (mutlak)",
    64: "Dikey konum (yer/AGL)",
}


def _dot_style(color: str, size: int = 12) -> str:
    return f"background-color: {color}; border-radius: {size // 2}px;"


class SensorRow(QWidget):
    """Tek bir sensorun saglik durumunu gosteren satir (nokta + isim)."""

    def __init__(self, label: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        self.dot = QLabel()
        self.dot.setFixedSize(12, 12)
        self.dot.setStyleSheet(_dot_style("#6c7086"))
        layout.addWidget(self.dot)

        self.name_lbl = QLabel(label)
        self.name_lbl.setStyleSheet("color: #cdd6f4; font-weight: 600; font-size: 12px;")
        layout.addWidget(self.name_lbl)
        layout.addStretch()

    def set_state(self, healthy):
        """healthy: True (saglikli) / False (arizali) / None (raporlanmiyor)."""
        if healthy is None:
            self.dot.setStyleSheet(_dot_style("#45475a"))
            self.setToolTip("Bu arac icin raporlanmiyor")
        elif healthy:
            self.dot.setStyleSheet(_dot_style("#a6e3a1"))
            self.setToolTip("Saglikli")
        else:
            self.dot.setStyleSheet(_dot_style("#f38ba8"))
            self.setToolTip("HATALI / SAGLIKSIZ")

class IssueRow(QWidget):
    """Aktif PreArm listesindeki tek bir satir: ham metin (kucuk, gri) +
    varsa altinda sade Turkce aciklama (daha buyuk, vurgulu). Eslesme
    bulunamazsa sadece ham metin gosterilir - hicbir sey gizlenmez."""

    def __init__(self, raw_text: str, friendly_text):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        raw_lbl = QLabel(raw_text)
        raw_lbl.setWordWrap(True)
        raw_lbl.setStyleSheet(
            "color: #6c7086; font-size: 10px; font-family: monospace;"
        )
        layout.addWidget(raw_lbl)

        if friendly_text:
            friendly_lbl = QLabel(friendly_text)
            friendly_lbl.setWordWrap(True)
            friendly_lbl.setStyleSheet(
                "color: #f38ba8; font-size: 12px; font-weight: 700;"
            )
            layout.addWidget(friendly_lbl)

class PrearmPanel(QGroupBox):
    fence_settings_changed = pyqtSignal(bool, float)  # enabled, radius_m
    rtl_alt_changed = pyqtSignal(float)  # metre
    battery_fs_changed = pyqtSignal(bool, float)  # enabled, volt
    polygon_draw_toggled = pyqtSignal(bool)
    polygon_undo_requested = pyqtSignal()
    polygon_clear_requested = pyqtSignal()
    polygon_upload_requested = pyqtSignal()
    polygon_download_requested = pyqtSignal()
    rally_draw_toggled = pyqtSignal(bool)
    rally_undo_requested = pyqtSignal()
    rally_clear_requested = pyqtSignal()
    rally_upload_requested = pyqtSignal()
    rally_download_requested = pyqtSignal()

    def __init__(self):
        super().__init__("Pre-Arm / Guvenlik Kontrolleri")
        self._prearm_issues = {}  # {mesaj_metni: son_gorulme_ts}
        self._is_armed = False
        self._ekf_ok = None  # None: henuz veri yok

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.banner = QLabel("BAGLANTI BEKLENIYOR")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "background-color: #45475a; color: #cdd6f4; font-weight: 800; "
            "font-size: 13px; padding: 10px; border-radius: 8px;"
        )
        root.addWidget(self.banner)

        sensors_frame = QFrame()
        sensors_grid = QGridLayout(sensors_frame)
        sensors_grid.setSpacing(2)
        sensors_grid.setContentsMargins(0, 0, 0, 0)
        self.sensor_rows = {}
        for i, (key, label) in enumerate(SENSOR_LABELS.items()):
            row = SensorRow(label)
            self.sensor_rows[key] = row
            sensors_grid.addWidget(row, i // 2, i % 2)
        root.addWidget(sensors_frame)

        ekf_row = QHBoxLayout()
        ekf_title = QLabel("EKF:")
        ekf_title.setStyleSheet("color: #cdd6f4; font-weight: 700; font-size: 12px;")
        ekf_row.addWidget(ekf_title)
        self.ekf_dot = QLabel()
        self.ekf_dot.setFixedSize(12, 12)
        self.ekf_dot.setStyleSheet(_dot_style("#6c7086"))
        ekf_row.addWidget(self.ekf_dot)
        self.ekf_label = QLabel("Bilinmiyor")
        self.ekf_label.setStyleSheet("color: #a6adc8; font-size: 12px; font-weight: 600;")
        ekf_row.addWidget(self.ekf_label)
        ekf_row.addStretch()
        root.addLayout(ekf_row)

        issues_title = QLabel("Aktif PreArm Uyarilari")
        issues_title.setStyleSheet("color: #cdd6f4; font-weight: 700; font-size: 12px;")
        root.addWidget(issues_title)

        self.issue_list = QListWidget()
        self.issue_list.setMaximumHeight(170)
        self.issue_list.setStyleSheet(
            "QListWidget { background-color: #11111b; border: 1px solid #313244; "
            "border-radius: 6px; color: #f38ba8; font-size: 11px; padding: 4px; }"
            "QListWidget::item { padding: 3px 2px; }"
        )
        root.addWidget(self.issue_list)

        fence_title = QLabel("Geofence Ayarlari")
        fence_title.setStyleSheet("color: #cdd6f4; font-weight: 700; font-size: 12px; margin-top: 6px;")
        root.addWidget(fence_title)

        fence_row = QHBoxLayout()
        self.fence_checkbox = QCheckBox("Aktif")
        self.fence_checkbox.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: 600;")
        fence_row.addWidget(self.fence_checkbox)

        fence_row.addWidget(QLabel("Yaricap (m):"))
        self.fence_radius_spin = QSpinBox()
        self.fence_radius_spin.setRange(10, 5000)
        self.fence_radius_spin.setValue(100)
        fence_row.addWidget(self.fence_radius_spin)

        self.fence_apply_btn = QPushButton("Uygula")
        self.fence_apply_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; padding: 6px 12px; border-radius: 6px;"
        )
        self.fence_apply_btn.clicked.connect(self._on_fence_apply_clicked)
        fence_row.addWidget(self.fence_apply_btn)
        fence_row.addStretch()
        root.addLayout(fence_row)

        fs_title = QLabel("Failsafe Ayarlari")
        fs_title.setStyleSheet("color: #cdd6f4; font-weight: 700; font-size: 12px; margin-top: 10px;")
        root.addWidget(fs_title)

        rtl_row = QHBoxLayout()
        rtl_row.addWidget(QLabel("RTL Irtifasi (m):"))
        self.rtl_alt_spin = QSpinBox()
        self.rtl_alt_spin.setRange(1, 200)
        self.rtl_alt_spin.setValue(15)
        rtl_row.addWidget(self.rtl_alt_spin)
        self.rtl_apply_btn = QPushButton("Uygula")
        self.rtl_apply_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; padding: 6px 12px; border-radius: 6px;"
        )
        self.rtl_apply_btn.clicked.connect(
            lambda: self.rtl_alt_changed.emit(float(self.rtl_alt_spin.value()))
        )
        rtl_row.addWidget(self.rtl_apply_btn)
        rtl_row.addStretch()
        root.addLayout(rtl_row)

        batt_row = QHBoxLayout()
        self.batt_fs_checkbox = QCheckBox("Pil Failsafe Aktif")
        self.batt_fs_checkbox.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: 600;")
        batt_row.addWidget(self.batt_fs_checkbox)
        batt_row.addWidget(QLabel("Esik (Volt):"))
        self.batt_fs_volt_spin = QSpinBox()
        self.batt_fs_volt_spin.setRange(0, 30)
        self.batt_fs_volt_spin.setValue(10)
        batt_row.addWidget(self.batt_fs_volt_spin)
        self.batt_fs_apply_btn = QPushButton("Uygula")
        self.batt_fs_apply_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: 800; padding: 6px 12px; border-radius: 6px;"
        )
        self.batt_fs_apply_btn.clicked.connect(
            lambda: self.battery_fs_changed.emit(
                self.batt_fs_checkbox.isChecked(), float(self.batt_fs_volt_spin.value())
            )
        )
        batt_row.addWidget(self.batt_fs_apply_btn)
        batt_row.addStretch()
        root.addLayout(batt_row)        

        self._rally_bolumu_ekle(root)

        poly_title = QLabel("Poligon Geofence")
        poly_title.setStyleSheet("color: #cdd6f4; font-weight: 700; font-size: 12px; margin-top: 10px;")
        root.addWidget(poly_title)

        self.polygon_draw_btn = QPushButton("Poligon Ciz")
        self.polygon_draw_btn.setCheckable(True)
        self.polygon_draw_btn.setStyleSheet(
            "background-color: #313244; color: #cdd6f4; font-weight: 700; padding: 6px 12px; border-radius: 6px;"
        )
        self.polygon_draw_btn.clicked.connect(
            lambda: self.polygon_draw_toggled.emit(self.polygon_draw_btn.isChecked())
        )
        root.addWidget(self.polygon_draw_btn)

        self.polygon_point_label = QLabel("0 nokta")
        self.polygon_point_label.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: 600;")
        root.addWidget(self.polygon_point_label)

        poly_btn_row1 = QHBoxLayout()
        self.polygon_undo_btn = QPushButton("Son Noktayi Sil")
        self.polygon_undo_btn.clicked.connect(self.polygon_undo_requested.emit)
        poly_btn_row1.addWidget(self.polygon_undo_btn)
        self.polygon_clear_btn = QPushButton("Temizle")
        self.polygon_clear_btn.clicked.connect(self.polygon_clear_requested.emit)
        poly_btn_row1.addWidget(self.polygon_clear_btn)
        root.addLayout(poly_btn_row1)

        poly_btn_row2 = QHBoxLayout()
        self.polygon_upload_btn = QPushButton("Poligonu FC'ye Yukle")
        self.polygon_upload_btn.setStyleSheet(
            "background-color: #a6e3a1; color: #1e1e2e; font-weight: 800; padding: 6px 12px; border-radius: 6px;"
        )
        self.polygon_upload_btn.clicked.connect(self.polygon_upload_requested.emit)
        poly_btn_row2.addWidget(self.polygon_upload_btn)
        self.polygon_download_btn = QPushButton("FC'den Indir")
        self.polygon_download_btn.clicked.connect(self.polygon_download_requested.emit)
        poly_btn_row2.addWidget(self.polygon_download_btn)
        root.addLayout(poly_btn_row2)
    def _rally_bolumu_ekle(self, root):
        """Acil inis (rally) noktalari bolumu.

        ArduPilot failsafe tetiklendiginde, RTL yerine EN YAKIN rally
        noktasina gidebilir. Bu yuzden noktalar gercekten inise uygun,
        acik ve engelsiz yerler olmalidir."""
        baslik = QLabel("Acil Inis Noktalari (Rally)")
        baslik.setStyleSheet(
            "color: #cdd6f4; font-weight: 700; font-size: 12px; margin-top: 10px;"
        )
        root.addWidget(baslik)

        aciklama = QLabel(
            "Failsafe durumunda arac eve degil, en yakin rally noktasina donebilir."
        )
        aciklama.setWordWrap(True)
        aciklama.setStyleSheet("color: #6c7086; font-size: 10px;")
        root.addWidget(aciklama)

        self.rally_draw_btn = QPushButton("Rally Noktasi Ekle")
        self.rally_draw_btn.setCheckable(True)
        self.rally_draw_btn.setStyleSheet(
            "background-color: #313244; color: #cdd6f4; font-weight: 700; "
            "padding: 6px 12px; border-radius: 6px;"
        )
        self.rally_draw_btn.clicked.connect(
            lambda: self.rally_draw_toggled.emit(self.rally_draw_btn.isChecked())
        )
        root.addWidget(self.rally_draw_btn)

        self.rally_point_label = QLabel("0 nokta")
        self.rally_point_label.setStyleSheet(
            "color: #a6adc8; font-size: 11px; font-weight: 600;"
        )
        root.addWidget(self.rally_point_label)

        satir1 = QHBoxLayout()
        self.rally_undo_btn = QPushButton("Son Noktayi Sil")
        self.rally_undo_btn.clicked.connect(self.rally_undo_requested.emit)
        satir1.addWidget(self.rally_undo_btn)
        self.rally_clear_btn = QPushButton("Temizle")
        self.rally_clear_btn.clicked.connect(self.rally_clear_requested.emit)
        satir1.addWidget(self.rally_clear_btn)
        root.addLayout(satir1)

        satir2 = QHBoxLayout()
        self.rally_upload_btn = QPushButton("Rally'yi FC'ye Yukle")
        self.rally_upload_btn.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: 800; "
            "padding: 6px 12px; border-radius: 6px;"
        )
        self.rally_upload_btn.clicked.connect(self.rally_upload_requested.emit)
        satir2.addWidget(self.rally_upload_btn)
        self.rally_download_btn = QPushButton("FC'den Indir")
        self.rally_download_btn.clicked.connect(self.rally_download_requested.emit)
        satir2.addWidget(self.rally_download_btn)
        root.addLayout(satir2)

    def set_rally_count(self, sayi: int):
        self.rally_point_label.setText(f"{sayi} nokta")

    def set_rally_draw_active(self, aktif: bool):
        self.rally_draw_btn.setChecked(bool(aktif))
        self.rally_draw_btn.setText(
            "Rally Ekleme: ACIK" if aktif else "Rally Noktasi Ekle"
        )

    # ---------------- telemetri girisleri ----------------

    def set_armed(self, is_armed: bool):
        self._is_armed = bool(is_armed)
        self._refresh_banner()

    def process_sys_status(self, data: dict):
        sensors = data.get("sensors") or {}
        for key, row in self.sensor_rows.items():
            row.set_state(sensors.get(key))
        self._refresh_banner()

    def process_ekf_status(self, data: dict):
        flags = int(data.get("flags", 0))
        ok = (flags & _EKF_REQUIRED_FLAGS) == _EKF_REQUIRED_FLAGS
        self._ekf_ok = ok
        if ok:
            self.ekf_dot.setStyleSheet(_dot_style("#a6e3a1"))
            self.ekf_label.setText("Saglikli")
        else:
            self.ekf_dot.setStyleSheet(_dot_style("#f38ba8"))
            # Sadece "sorunlu" demek yerine, TAM OLARAK hangi tahminlerin
            # (yatay konum, dikey hiz vb.) guvenilmez oldugunu listele.
            missing = [
                label for bit, label in _EKF_FLAG_LABELS.items()
                if (bit & _EKF_REQUIRED_FLAGS) and not (flags & bit)
            ]
            if missing:
                self.ekf_label.setText("Sorunlu: " + ", ".join(missing))
            else:
                self.ekf_label.setText("Sorunlu (detay yok)")
        self._refresh_banner()

    def process_statustext(self, data: dict):
        text = (data.get("text") or "").strip()
        if not text:
            return
        severity = int(data.get("severity", 6))
        lower = text.lower()
        is_prearm = "prearm" in lower
        is_fence = "fence" in lower
        # MAV_SEVERITY: 0 EMERGENCY .. 3 ERROR .. 4 WARNING .. 6 INFO .. 7 DEBUG
        # PreArm mesajlari, fence ile ilgili mesajlar (genelde WARNING
        # seviyesinde gelir, ERROR esigini gecmez) veya ERROR ve daha
        # ciddi olanlari takip ediyoruz.
        if is_prearm or is_fence or severity <= 3:
            self._prearm_issues[text] = time.time()
            self._refresh_issue_list()
            self._refresh_banner()

    def tick(self):
        """Periyodik cagrilmali. Bir sureden uzun tekrarlanmayan PreArm
        mesajlarini (cozulmus kabul edip) listeden dusurur."""
        now = time.time()
        stale = [t for t, ts in self._prearm_issues.items() if now - ts > PREARM_STALE_S]
        if stale:
            for t in stale:
                del self._prearm_issues[t]
            self._refresh_issue_list()
            self._refresh_banner()

    def reset_connection_state(self):
        """Baglanti koptugunda / yeniden baglanmadan once cagrilir."""
        self._prearm_issues.clear()
        self._ekf_ok = None
        self._is_armed = False
        for row in self.sensor_rows.values():
            row.set_state(None)
        self.ekf_dot.setStyleSheet(_dot_style("#6c7086"))
        self.ekf_label.setText("Bilinmiyor")
        self._refresh_issue_list()
        self.banner.setText("BAGLANTI BEKLENIYOR")
        self.banner.setStyleSheet(
            "background-color: #45475a; color: #cdd6f4; font-weight: 800; "
            "font-size: 13px; padding: 10px; border-radius: 8px;"
        )
    def get_ekf_ok(self):
        """Uctan uca kontrol listesi gibi disaridan sorgulamalar icin
        EKF durumunu dondurur: True/False/None (henuz veri yok)."""
        return self._ekf_ok

    def get_active_issue_count(self):
        """Su anda aktif (cozulmemis) PreArm uyari sayisini dondurur."""
        return len(self._prearm_issues)
    # ---------------- ic yardimcilar ----------------

    def _refresh_issue_list(self):
        self.issue_list.clear()
        for text in sorted(self._prearm_issues.keys()):
            friendly = translate_prearm_text(text)
            row = IssueRow(text, friendly)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.issue_list.addItem(item)
            self.issue_list.setItemWidget(item, row)
    def _on_fence_apply_clicked(self):
        self.fence_settings_changed.emit(
            self.fence_checkbox.isChecked(),
            float(self.fence_radius_spin.value()),
        )

    def set_fence_display(self, enabled, radius):
        """FC'den gelen guncel FENCE_ENABLE/FENCE_RADIUS degerlerini
        checkbox/spinbox'a yansitir - kullanicinin yazdigi deger degil,
        FC'nin gercekten uyguladigi deger gosterilir."""
        self.fence_checkbox.blockSignals(True)
        self.fence_checkbox.setChecked(bool(enabled))
        self.fence_checkbox.blockSignals(False)
        if radius is not None:
            self.fence_radius_spin.blockSignals(True)
            self.fence_radius_spin.setValue(int(radius))
            self.fence_radius_spin.blockSignals(False)

    def set_failsafe_display(self, rtl_alt_m, batt_fs_enabled, batt_fs_volt):
        """FC'den gelen guncel RTL_ALT/BATT_LOW_VOLT/FS_BATT_ENABLE
        degerlerini ilgili alanlara yansitir."""
        if rtl_alt_m is not None:
            self.rtl_alt_spin.blockSignals(True)
            self.rtl_alt_spin.setValue(int(rtl_alt_m))
            self.rtl_alt_spin.blockSignals(False)
        if batt_fs_enabled is not None:
            self.batt_fs_checkbox.blockSignals(True)
            self.batt_fs_checkbox.setChecked(bool(batt_fs_enabled))
            self.batt_fs_checkbox.blockSignals(False)
        if batt_fs_volt is not None:
            self.batt_fs_volt_spin.blockSignals(True)
            self.batt_fs_volt_spin.setValue(int(batt_fs_volt))
            self.batt_fs_volt_spin.blockSignals(False)

    def set_polygon_point_count(self, count: int):
        self.polygon_point_label.setText(f"{count} nokta")

    def set_polygon_button_checked(self, checked: bool):
        self.polygon_draw_btn.blockSignals(True)
        self.polygon_draw_btn.setChecked(checked)
        self.polygon_draw_btn.blockSignals(False)
    def _refresh_banner(self):
        if self._is_armed:
            self.banner.setText("ARMED — kontroller devre disi")
            self.banner.setStyleSheet(
                "background-color: #313244; color: #a6adc8; font-weight: 800; "
                "font-size: 13px; padding: 10px; border-radius: 8px;"
            )
            return

        if self._prearm_issues:
            n = len(self._prearm_issues)
            self.banner.setText(f"ARM'A HAZIR DEGIL ({n} sorun)")
            self.banner.setStyleSheet(
                "background-color: #f38ba8; color: #1e1e2e; font-weight: 800; "
                "font-size: 13px; padding: 10px; border-radius: 8px;"
            )
        elif self._ekf_ok is False:
            self.banner.setText("ARM'A HAZIR DEGIL (EKF sorunlu)")
            self.banner.setStyleSheet(
                "background-color: #f9e2af; color: #1e1e2e; font-weight: 800; "
                "font-size: 13px; padding: 10px; border-radius: 8px;"
            )
        elif self._ekf_ok is True:
            self.banner.setText("ARM'A HAZIR")
            self.banner.setStyleSheet(
                "background-color: #a6e3a1; color: #1e1e2e; font-weight: 800; "
                "font-size: 13px; padding: 10px; border-radius: 8px;"
            )
        else:
            self.banner.setText("EKF / sensor verisi bekleniyor")
            self.banner.setStyleSheet(
                "background-color: #45475a; color: #cdd6f4; font-weight: 800; "
                "font-size: 13px; padding: 10px; border-radius: 8px;"
            )
