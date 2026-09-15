"""
test_mission_modes.py
----------------------
ADIM 7 + 8 arayuz dogrulamasi.

Gorev modlarinin GERCEK bir davranisi olmali (sadece kart gizleyip renk
degistirmemeli) ve gorev yuklenmeden once guvenlik sorunlari
gosterilmeli.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QMessageBox

from gui_harness import qt_app

from core.mission_analysis import HATA
from ui.mission_panel import MissionPanel
from ui.pattern_dialog import MOD_ARAMA, MOD_HARITALAMA, PatternDialog

# Kenarlari ~670 x ~855 m olan alan
ALAN = [
    (39.9200, 32.8600, 30.0),
    (39.9200, 32.8700, 30.0),
    (39.9260, 32.8700, 30.0),
    (39.9260, 32.8600, 30.0),
]
HOME = (39.9200, 32.8600)

# Kenarlari ~100 m olan kucuk alan: 200 m kenar payi bunu tamamen yer.
KUCUK_ALAN = [
    (39.9200, 32.8600, 30.0),
    (39.9200, 32.8612, 30.0),
    (39.9209, 32.8612, 30.0),
    (39.9209, 32.8600, 30.0),
]


class ModDavranisiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        self.panel = MissionPanel()
        self.addCleanup(self.panel.deleteLater)

    def test_standart_modda_rota_uretme_butonu_gizli(self):
        self.panel.set_mission_mode("Standart")
        self.assertFalse(self.panel.btn_pattern.isVisible())

    def test_haritalama_modunda_buton_gorunur(self):
        self.panel.show()
        self.panel.set_mission_mode(MOD_HARITALAMA)
        self.assertTrue(self.panel.btn_pattern.isVisible())
        self.assertIn("TARAYAN", self.panel.btn_pattern.text())

    def test_arama_modunda_buton_metni_degisir(self):
        self.panel.show()
        self.panel.set_mission_mode(MOD_ARAMA)
        self.assertTrue(self.panel.btn_pattern.isVisible())
        self.assertIn("ARAMA", self.panel.btn_pattern.text())

    def test_yetersiz_nokta_ile_uretim_engellenir(self):
        """Haritalama icin 3 nokta sart; eksikse bilgi penceresi cikar."""
        self.panel.set_mission_mode(MOD_HARITALAMA)
        self.panel.waypoints = [(39.92, 32.86, 30.0)]
        cagrildi = []
        orijinal = QMessageBox.information
        QMessageBox.information = lambda *a, **k: cagrildi.append(a)
        try:
            self.panel.on_pattern_clicked()
        finally:
            QMessageBox.information = orijinal
        self.assertTrue(cagrildi, "Eksik nokta uyarisi verilmedi")
        self.assertEqual(len(self.panel.waypoints), 1, "Rota yine de uretildi")


class PatternDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def test_haritalama_rotasi_uretilir(self):
        d = PatternDialog(MOD_HARITALAMA, ALAN)
        self.addCleanup(d.deleteLater)
        d.spin_aralik.setValue(100.0)
        d._uret()
        rota = d.get_waypoints()
        self.assertGreater(len(rota), len(ALAN))
        for nokta in rota:
            self.assertEqual(len(nokta), 3, "Nokta (lat, lon, alt) olmali")

    def test_uretilen_noktalar_secilen_irtifayi_alir(self):
        d = PatternDialog(MOD_HARITALAMA, ALAN)
        self.addCleanup(d.deleteLater)
        d.spin_irtifa.setValue(55.0)
        d._uret()
        for _lat, _lon, alt in d.get_waypoints():
            self.assertEqual(alt, 55.0)

    def test_kameradan_hat_araligi_hesaplanir(self):
        d = PatternDialog(MOD_HARITALAMA, ALAN)
        self.addCleanup(d.deleteLater)
        d.combo_kaynak.setCurrentIndex(1)  # kameradan
        d.spin_irtifa.setValue(100.0)
        d.spin_fov.setValue(90.0)
        d.spin_ortusme.setValue(0)
        self.assertAlmostEqual(d._hat_araligi(), 200.0, places=3)
        d.spin_ortusme.setValue(50)
        self.assertAlmostEqual(d._hat_araligi(), 100.0, places=3)

    def test_arama_deseni_uretilir(self):
        d = PatternDialog(MOD_ARAMA, [(39.925, 32.866, 30.0)])
        self.addCleanup(d.deleteLater)
        d.spin_bacak.setValue(8)
        d._uret()
        self.assertEqual(len(d.get_waypoints()), 9)  # bacak + 1

    def test_alandan_buyuk_aralik_tek_hat_verir(self):
        """Hata degil: genis tarama seridi tek gecisle kapanir."""
        d = PatternDialog(MOD_HARITALAMA, ALAN)
        self.addCleanup(d.deleteLater)
        d.spin_aralik.setValue(5000.0)
        d._uret()
        self.assertEqual(len(d.get_waypoints()), 2)

    def test_gecersiz_ayarda_uret_butonu_kapanir(self):
        """Kenar payi alani tamamen yerse onizleme hata gosterir ve
        URET butonu kapanir."""
        from PyQt5.QtWidgets import QDialogButtonBox

        d = PatternDialog(MOD_HARITALAMA, KUCUK_ALAN)
        self.addCleanup(d.deleteLater)
        d.spin_pay.setValue(200.0)  # ~100 m'lik alani tamamen yer
        d._onizlemeyi_guncelle()
        self.assertFalse(d.butonlar.button(QDialogButtonBox.Ok).isEnabled())
        self.assertIn("sigmiyor", d.lbl_onizleme.text().lower())

    def test_onizleme_nokta_ve_mesafe_gosterir(self):
        d = PatternDialog(MOD_HARITALAMA, ALAN)
        self.addCleanup(d.deleteLater)
        d.spin_aralik.setValue(100.0)
        d._onizlemeyi_guncelle()
        metin = d.lbl_onizleme.text()
        self.assertIn("nokta", metin)
        self.assertTrue("km" in metin or " m " in metin, metin)


class AnalizArayuzuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        self.panel = MissionPanel()
        self.addCleanup(self.panel.deleteLater)

    def test_bos_gorevde_bilgilendirme_metni(self):
        self.assertIn("gorunur", self.panel.lbl_analiz.text())

    def test_waypoint_eklenince_ozet_cikar(self):
        self.panel.set_analysis_context(home=HOME)
        self.panel.waypoints = [(39.9250, 32.8600, 30.0)]
        self.panel._refresh_table()
        self.assertIn("nokta", self.panel.lbl_analiz.text())

    def test_geofence_ihlali_analizde_gorunur(self):
        self.panel.set_analysis_context(
            home=HOME, fence={"enabled": True, "radius_m": 100}
        )
        self.panel.waypoints = [(39.9400, 32.8600, 30.0)]  # ~2.2 km
        analiz = self.panel.analyze()
        hatalar = [u for u in analiz["uyarilar"] if u["seviye"] == HATA]
        self.assertTrue(hatalar)
        self.panel._refresh_table()
        self.assertIn("guvenlik", self.panel.lbl_analiz.text().lower())

    def test_ihlalli_gorev_onay_ister_ve_hayir_denince_yuklenmez(self):
        self.panel.set_analysis_context(
            home=HOME, fence={"enabled": True, "radius_m": 100}
        )
        self.panel.waypoints = [(39.9400, 32.8600, 30.0)]
        yuklenenler = []
        self.panel.upload_requested.connect(yuklenenler.append)

        orijinal = QMessageBox.warning
        QMessageBox.warning = lambda *a, **k: QMessageBox.No
        try:
            self.panel.on_upload_clicked()
        finally:
            QMessageBox.warning = orijinal
        self.assertEqual(yuklenenler, [], "Onay verilmeden gorev yuklendi")

    def test_ihlalli_gorev_onaylanirsa_yuklenir(self):
        self.panel.set_analysis_context(
            home=HOME, fence={"enabled": True, "radius_m": 100}
        )
        self.panel.waypoints = [(39.9400, 32.8600, 30.0)]
        yuklenenler = []
        self.panel.upload_requested.connect(yuklenenler.append)

        orijinal = QMessageBox.warning
        QMessageBox.warning = lambda *a, **k: QMessageBox.Yes
        try:
            self.panel.on_upload_clicked()
        finally:
            QMessageBox.warning = orijinal
        self.assertEqual(len(yuklenenler), 1)

    def test_temiz_gorev_onay_istemeden_yuklenir(self):
        self.panel.set_analysis_context(
            home=HOME, fence={"enabled": True, "radius_m": 5000}
        )
        self.panel.waypoints = [(39.9250, 32.8600, 30.0)]
        yuklenenler = []
        self.panel.upload_requested.connect(yuklenenler.append)

        cagrildi = []
        orijinal = QMessageBox.warning
        QMessageBox.warning = lambda *a, **k: cagrildi.append(a) or QMessageBox.Yes
        try:
            self.panel.on_upload_clicked()
        finally:
            QMessageBox.warning = orijinal
        self.assertEqual(cagrildi, [], "Temiz gorevde gereksiz onay istendi")
        self.assertEqual(len(yuklenenler), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
