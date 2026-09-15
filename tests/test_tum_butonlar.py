"""
test_tum_butonlar.py
---------------------
Kapsam taramasi: arayuzdeki HER butona basilir ve hicbirinin istisna
firlatmadigi dogrulanir.

Neden gerekli: tek tek ozellik testleri, nadir kullanilan bir butonun
(orn. baglanti yokken "FC'den Indir") cokup cokmedigini kacirabilir.
Bu test butonlari kaba kuvvetle gezer.

Modal pencereler (QMessageBox, QFileDialog) testin kilitlenmemesi icin
gecici olarak degistirilir.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
    QPushButton,
)

from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump

# Basilmasi testi anlamsiz yapan veya sureci degistiren butonlar.
ATLANACAK_METINLER = {
    "Kapat",        # dialog kapatir
    "Iptal",
}


class ModalKapatici:
    """QMessageBox / QFileDialog / QDialog.exec_ cagrilarini yutar."""

    def __enter__(self):
        self._orijinal = {
            "information": QMessageBox.information,
            "warning": QMessageBox.warning,
            "critical": QMessageBox.critical,
            "question": QMessageBox.question,
            "getSaveFileName": QFileDialog.getSaveFileName,
            "getOpenFileName": QFileDialog.getOpenFileName,
            "exec_": QDialog.exec_,
        }
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.No)
        QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
        QDialog.exec_ = lambda self_: QDialog.Rejected
        return self

    def __exit__(self, *exc):
        QMessageBox.information = self._orijinal["information"]
        QMessageBox.warning = self._orijinal["warning"]
        QMessageBox.critical = self._orijinal["critical"]
        QMessageBox.question = self._orijinal["question"]
        QFileDialog.getSaveFileName = self._orijinal["getSaveFileName"]
        QFileDialog.getOpenFileName = self._orijinal["getOpenFileName"]
        QDialog.exec_ = self._orijinal["exec_"]
        return False


class TumButonlarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.mission_protocol = True
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected, "Sahte araca baglanilamadi"

    @classmethod
    def tearDownClass(cls):
        cls.win.voice.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()

    def _butonlari_bas(self, kok, baslik):
        """kok altindaki tum butonlara basar, istisna firlatanlari toplar."""
        hatalar = []
        basilan = 0
        butonlar = [
            b for b in kok.findChildren(QPushButton)
            if b.text() not in ATLANACAK_METINLER
        ]
        self.assertGreater(len(butonlar), 0, f"{baslik}: hic buton bulunamadi")

        with ModalKapatici():
            for btn in butonlar:
                ad = btn.objectName() or btn.text() or "<isimsiz>"
                try:
                    btn.click()
                    QApplication.processEvents()
                except Exception as e:
                    hatalar.append(f"{ad}: {type(e).__name__}: {e}")
                basilan += 1
        pump(0.3)
        self._worker_bosalsin()
        return basilan, hatalar

    def _worker_bosalsin(self, saniye=25.0):
        """Butonlara basmak FC'ye giden yavas komutlari (gorev indir, fence
        indir, rally indir...) kuyruga atar. Her biri saniyeler surebilir;
        bir sonraki testin bunlari beklemesi gerekir, yoksa telemetri
        guncellemeleri gecikir ve test yanlislikla basarisiz olur."""
        worker = self.win.worker
        if worker is None:
            return
        pump(saniye, until=lambda: worker.command_queue.empty())
        pump(0.5)

    def test_ana_penceredeki_tum_butonlar_baglantiliyken(self):
        sayi, hatalar = self._butonlari_bas(self.win, "ana pencere (bagli)")
        self.assertEqual(hatalar, [], f"{sayi} butondan hata verenler")

    def test_her_sekmedeki_butonlar(self):
        """Sekmeler arasinda gezerken de butonlar calismali."""
        tum_hatalar = []
        for i in range(self.win.tabs.count()):
            self.win.tabs.setCurrentIndex(i)
            pump(0.2)
            _sayi, hatalar = self._butonlari_bas(
                self.win.tabs.widget(i), f"sekme {self.win.tabs.tabText(i)}"
            )
            tum_hatalar += [f"[{self.win.tabs.tabText(i)}] {h}" for h in hatalar]
        self.assertEqual(tum_hatalar, [])

    def test_gorev_modlari_arasinda_gecis(self):
        """Mod degisimi sekmeleri yeniden diziyor; bu sirada hicbir sey
        kaybolmamali ve butonlar calismaya devam etmeli."""
        tum_hatalar = []
        for mod in ("Haritalama", "Arama Kurtarma", "Standart"):
            self.win.on_mission_mode_changed(mod)
            pump(0.3)
            self.assertEqual(self.win.mission_mode, mod)
            self.assertEqual(
                self.win.tabs.count(), 5, f"{mod} modunda sekme kayboldu"
            )
            _sayi, hatalar = self._butonlari_bas(self.win, f"mod {mod}")
            tum_hatalar += [f"[{mod}] {h}" for h in hatalar]
        self.assertEqual(tum_hatalar, [])

    def test_kalibrasyon_sihirbazindaki_butonlar(self):
        self.win.on_calibration_clicked()
        pump(0.3)
        dialog = self.win.calibration_dialog
        self.assertIsNotNone(dialog)
        try:
            _sayi, hatalar = self._butonlari_bas(dialog, "kalibrasyon")
            self.assertEqual(hatalar, [])
        finally:
            dialog.close()
            pump(0.2)

    def test_baglanti_yokken_butonlar_cokmez(self):
        """En sik atlanan durum: FC bagli degilken FC'ye komut gonderen
        butonlara basmak."""
        self.win.connected = False
        try:
            sayi, hatalar = self._butonlari_bas(self.win, "baglanti yok")
            self.assertEqual(hatalar, [], f"{sayi} butondan hata verenler")
        finally:
            self.win.connected = True

    def test_worker_yokken_butonlar_cokmez(self):
        """Baglanti kopup worker yok edildiginde de arayuz dayanmali.

        Worker GERCEKTEN durdurulur; sadece referansi None yapmak, calisan
        thread'i soketi tutarken birakir ve sonraki baglanti port
        cakismasina duser."""
        eski = self.win.worker
        if eski is not None:
            self.win._disconnect_worker(eski)
            eski.stop()
        self.win.worker = None
        self.win.connected = False
        try:
            _sayi, hatalar = self._butonlari_bas(self.win, "worker yok")
            self.assertEqual(hatalar, [])
        finally:
            # Diger testler icin calisir bir baglanti birak.
            self.win._start_worker()
            pump(8.0, until=lambda: self.win.connected)

    def test_arm_durumdayken_butonlar_cokmez(self):
        self._worker_bosalsin()
        self.vehicle.armed = True
        self.assertTrue(
            pump(15.0, until=lambda: self.win.is_armed),
            "ARM durumu arayuze yansimadi",
        )
        try:
            _sayi, hatalar = self._butonlari_bas(self.win, "ARM durumda")
            self.assertEqual(hatalar, [])
        finally:
            self.vehicle.armed = False
            pump(15.0, until=lambda: not self.win.is_armed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
