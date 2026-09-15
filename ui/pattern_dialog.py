"""
pattern_dialog.py
------------------
Otomatik rota uretme penceresi (gorev modlarinin arayuzu).

  Haritalama      -> mevcut waypoint'ler bir POLIGON tanimlar; icini
                     tarayan gidis-donus rotasi uretilir.
  Arama Kurtarma  -> ilk waypoint MERKEZ kabul edilir; genisleyen kare
                     arama deseni uretilir.

Mevcut noktalari alan tanimi olarak kullanmak bilincli bir tercihtir:
haritada ayri bir cizim modu gerektirmez, kullanici zaten bildigi sekilde
noktalari tiklar.

Pencere MAVLink'e dokunmaz; yalnizca `core.mission_planner` geometrisini
cagirir ve sonucu `get_waypoints()` ile dondurur.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.mission_analysis import mesafe_metni, sure_metni
from core.mission_planner import (
    expanding_square,
    polygon_area_m2,
    route_length_m,
    spacing_from_camera,
    survey_grid,
)

MOD_HARITALAMA = "Haritalama"
MOD_ARAMA = "Arama Kurtarma"

# Rota uretiminde kullanilan varsayilan seyir hizi (bkz. mission_analysis).
ONIZLEME_HIZI_MS = 5.0


class PatternDialog(QDialog):
    def __init__(self, mode: str, waypoints, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Otomatik Rota Uret — {mode}")
        self.setMinimumWidth(460)
        self.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4;")

        self._mode = mode
        self._kaynak_noktalar = list(waypoints or [])
        self._sonuc = []

        root = QVBoxLayout(self)

        self.lbl_kaynak = QLabel()
        self.lbl_kaynak.setWordWrap(True)
        self.lbl_kaynak.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; "
            "border-radius: 8px; padding: 10px; color: #a6adc8;"
        )
        root.addWidget(self.lbl_kaynak)

        if mode == MOD_HARITALAMA:
            root.addWidget(self._haritalama_kutusu())
        else:
            root.addWidget(self._arama_kutusu())

        irtifa_kutu = QGroupBox("Rota Irtifasi")
        irtifa_form = QFormLayout()
        self.spin_irtifa = QDoubleSpinBox()
        self.spin_irtifa.setRange(1.0, 500.0)
        self.spin_irtifa.setValue(self._varsayilan_irtifa())
        self.spin_irtifa.setSuffix(" m")
        self.spin_irtifa.valueChanged.connect(self._onizlemeyi_guncelle)
        irtifa_form.addRow("Tum noktalar icin irtifa", self.spin_irtifa)
        irtifa_kutu.setLayout(irtifa_form)
        root.addWidget(irtifa_kutu)

        self.lbl_onizleme = QLabel()
        self.lbl_onizleme.setWordWrap(True)
        self.lbl_onizleme.setAlignment(Qt.AlignCenter)
        self.lbl_onizleme.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; "
            "border-radius: 10px; padding: 12px; font-weight: 700;"
        )
        root.addWidget(self.lbl_onizleme)

        self.butonlar = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.butonlar.button(QDialogButtonBox.Ok).setText("ROTAYI URET")
        self.butonlar.button(QDialogButtonBox.Cancel).setText("Iptal")
        self.butonlar.accepted.connect(self._uret)
        self.butonlar.rejected.connect(self.reject)
        root.addWidget(self.butonlar)

        self._kaynak_metnini_guncelle()
        self._onizlemeyi_guncelle()

    # ---------------- mod kutulari ----------------

    def _haritalama_kutusu(self):
        kutu = QGroupBox("Tarama Ayarlari")
        form = QFormLayout()

        self.combo_kaynak = QComboBox()
        self.combo_kaynak.addItem("Dogrudan hat araligi gir", "dogrudan")
        self.combo_kaynak.addItem("Kameradan hesapla", "kamera")
        self.combo_kaynak.currentIndexChanged.connect(self._kaynak_degisti)
        form.addRow("Hat araligi kaynagi", self.combo_kaynak)

        self.yigin = QStackedWidget()

        # -- dogrudan --
        dogrudan = QWidget()
        d_form = QFormLayout(dogrudan)
        self.spin_aralik = QDoubleSpinBox()
        self.spin_aralik.setRange(1.0, 2000.0)
        self.spin_aralik.setValue(50.0)
        self.spin_aralik.setSuffix(" m")
        self.spin_aralik.valueChanged.connect(self._onizlemeyi_guncelle)
        d_form.addRow("Hat araligi", self.spin_aralik)
        self.yigin.addWidget(dogrudan)

        # -- kameradan --
        kamera = QWidget()
        k_form = QFormLayout(kamera)
        self.spin_fov = QDoubleSpinBox()
        self.spin_fov.setRange(10.0, 170.0)
        self.spin_fov.setValue(84.0)  # yaygin aksiyon kamerasi
        self.spin_fov.setSuffix(" °")
        self.spin_fov.valueChanged.connect(self._onizlemeyi_guncelle)
        k_form.addRow("Kamera gorus acisi (yatay)", self.spin_fov)

        self.spin_ortusme = QSpinBox()
        self.spin_ortusme.setRange(0, 90)
        self.spin_ortusme.setValue(30)
        self.spin_ortusme.setSuffix(" %")
        self.spin_ortusme.valueChanged.connect(self._onizlemeyi_guncelle)
        k_form.addRow("Yan ortusme", self.spin_ortusme)

        self.lbl_hesaplanan = QLabel("—")
        self.lbl_hesaplanan.setStyleSheet("color: #89dceb; font-weight: 700;")
        k_form.addRow("Hesaplanan hat araligi", self.lbl_hesaplanan)
        self.yigin.addWidget(kamera)

        form.addRow(self.yigin)

        self.spin_aci = QSpinBox()
        self.spin_aci.setRange(0, 179)
        self.spin_aci.setValue(0)
        self.spin_aci.setSuffix(" °")
        self.spin_aci.setToolTip("0 = dogu-bati hatlari, 90 = kuzey-guney")
        self.spin_aci.valueChanged.connect(self._onizlemeyi_guncelle)
        form.addRow("Hat yonu", self.spin_aci)

        self.spin_pay = QDoubleSpinBox()
        self.spin_pay.setRange(0.0, 200.0)
        self.spin_pay.setValue(0.0)
        self.spin_pay.setSuffix(" m")
        self.spin_pay.setToolTip("Alan kenarindan iceri birakilan guvenlik payi")
        self.spin_pay.valueChanged.connect(self._onizlemeyi_guncelle)
        form.addRow("Kenar payi", self.spin_pay)

        kutu.setLayout(form)
        return kutu

    def _arama_kutusu(self):
        kutu = QGroupBox("Arama Deseni Ayarlari")
        form = QFormLayout()

        self.spin_aralik = QDoubleSpinBox()
        self.spin_aralik.setRange(5.0, 1000.0)
        self.spin_aralik.setValue(50.0)
        self.spin_aralik.setSuffix(" m")
        self.spin_aralik.setToolTip(
            "Bacak uzunluklari bu degerin katlari olarak artar: d, d, 2d, 2d ..."
        )
        self.spin_aralik.valueChanged.connect(self._onizlemeyi_guncelle)
        form.addRow("Hat araligi", self.spin_aralik)

        self.spin_bacak = QSpinBox()
        self.spin_bacak.setRange(2, 60)
        self.spin_bacak.setValue(12)
        self.spin_bacak.valueChanged.connect(self._onizlemeyi_guncelle)
        form.addRow("Bacak sayisi", self.spin_bacak)

        self.spin_yon = QSpinBox()
        self.spin_yon.setRange(0, 359)
        self.spin_yon.setValue(0)
        self.spin_yon.setSuffix(" °")
        self.spin_yon.setToolTip("Ilk bacagin yonu — 0 = kuzey")
        self.spin_yon.valueChanged.connect(self._onizlemeyi_guncelle)
        form.addRow("Baslangic yonu", self.spin_yon)

        kutu.setLayout(form)
        return kutu

    # ---------------- yardimcilar ----------------

    def _varsayilan_irtifa(self):
        if self._kaynak_noktalar and len(self._kaynak_noktalar[0]) >= 3:
            return float(self._kaynak_noktalar[0][2])
        return 30.0

    def _kaynak_degisti(self, indeks):
        self.yigin.setCurrentIndex(indeks)
        self._onizlemeyi_guncelle()

    def _kaynak_metnini_guncelle(self):
        sayi = len(self._kaynak_noktalar)
        if self._mode == MOD_HARITALAMA:
            if sayi < 3:
                self.lbl_kaynak.setText(
                    f"Tarama alani icin EN AZ 3 nokta gerekli (su an {sayi}).\n"
                    "Haritaya tiklayarak alanin kosellerini isaretleyin."
                )
            else:
                alan = polygon_area_m2(
                    [(p[0], p[1]) for p in self._kaynak_noktalar]
                )
                self.lbl_kaynak.setText(
                    f"Tarama alani: {sayi} koseli poligon · "
                    f"{alan / 10000:.1f} hektar ({alan:,.0f} m²)\n"
                    "Uretilen rota mevcut noktalarin YERINE gecer."
                )
        else:
            if sayi < 1:
                self.lbl_kaynak.setText(
                    "Arama merkezi icin haritaya en az 1 nokta ekleyin."
                )
            else:
                merkez = self._kaynak_noktalar[0]
                self.lbl_kaynak.setText(
                    f"Arama merkezi: {merkez[0]:.6f}, {merkez[1]:.6f} "
                    f"(1. waypoint)\n"
                    "Uretilen rota mevcut noktalarin YERINE gecer."
                )

    def _hat_araligi(self):
        if self._mode != MOD_HARITALAMA:
            return self.spin_aralik.value()
        if self.combo_kaynak.currentData() == "kamera":
            aralik = spacing_from_camera(
                self.spin_irtifa.value(),
                self.spin_fov.value(),
                self.spin_ortusme.value() / 100.0,
            )
            self.lbl_hesaplanan.setText(f"{aralik:.1f} m")
            return aralik
        return self.spin_aralik.value()

    def _rota_uret(self):
        """Gecerli ayarlarla rotayi hesaplar. Hatali girdide ValueError."""
        if self._mode == MOD_HARITALAMA:
            poligon = [(p[0], p[1]) for p in self._kaynak_noktalar]
            noktalar = survey_grid(
                poligon,
                spacing_m=self._hat_araligi(),
                angle_deg=float(self.spin_aci.value()),
                margin_m=self.spin_pay.value(),
            )
        else:
            if not self._kaynak_noktalar:
                raise ValueError("Arama merkezi icin en az 1 nokta gerekli")
            merkez = (self._kaynak_noktalar[0][0], self._kaynak_noktalar[0][1])
            noktalar = expanding_square(
                merkez,
                spacing_m=self.spin_aralik.value(),
                legs=self.spin_bacak.value(),
                start_heading_deg=float(self.spin_yon.value()),
            )
        irtifa = self.spin_irtifa.value()
        return [(lat, lon, irtifa) for lat, lon in noktalar]

    def _onizlemeyi_guncelle(self):
        try:
            rota = self._rota_uret()
        except ValueError as e:
            self.lbl_onizleme.setText(str(e))
            self.lbl_onizleme.setStyleSheet(
                "background-color: #45262f; border: 1px solid #f38ba8; "
                "border-radius: 10px; padding: 12px; color: #f38ba8; font-weight: 700;"
            )
            self.butonlar.button(QDialogButtonBox.Ok).setEnabled(False)
            return

        uzunluk = route_length_m([(p[0], p[1]) for p in rota])
        self.lbl_onizleme.setText(
            f"{len(rota)} nokta · {mesafe_metni(uzunluk)} · "
            f"~{sure_metni(uzunluk / ONIZLEME_HIZI_MS)} "
            f"({ONIZLEME_HIZI_MS:.0f} m/s varsayimiyla)"
        )
        self.lbl_onizleme.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; "
            "border-radius: 10px; padding: 12px; color: #a6e3a1; font-weight: 700;"
        )
        self.butonlar.button(QDialogButtonBox.Ok).setEnabled(True)

    def _uret(self):
        try:
            self._sonuc = self._rota_uret()
        except ValueError:
            return
        self.accept()

    def get_waypoints(self):
        """Uretilen rota: [(lat, lon, alt), ...]. Iptal edilirse bos liste."""
        return list(self._sonuc)
