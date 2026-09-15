"""
test_saglamlik.py
------------------
Dayaniklilik: disk/izin hatalari ve temiz kapanma.

Kayit tutmak ucusun kendisinden daha az onemlidir. Salt-okunur klasor,
dolu disk veya cikarilmis USB durumunda kaydedici sessizce devre disi
kalmali; ARM rozetleri, ucus sayaci ve butonlar calismaya DEVAM etmeli.
"""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.flight_logger import FlightLogger
from fake_vehicle import FakeVehicle, free_udp_port
from gui_harness import boot_gcs, pump


class FlightLoggerHataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        # Izinleri geri ac ki temizlik yapilabilsin
        try:
            os.chmod(self.tmp.name, stat.S_IRWXU)
        except OSError:
            pass
        self.tmp.cleanup()

    def test_normal_durumda_kayit_acilir(self):
        logger = FlightLogger(log_dir=self.tmp.name)
        self.assertTrue(logger.start())
        self.assertTrue(logger.log_row(39.9, 32.8, 10, 3, 90, 80, "GUIDED", True))
        logger.stop()
        self.assertEqual(len(os.listdir(self.tmp.name)), 1)

    def test_yazilamayan_klasorde_istisna_firlatmaz(self):
        """ASIL REGRESYON: start() istisna firlatirsa ARM isleme yolu
        yarida kesilir ve rozetler guncellenmez."""
        hedef = os.path.join(self.tmp.name, "salt_okunur")
        os.makedirs(hedef)
        os.chmod(hedef, stat.S_IRUSR | stat.S_IXUSR)  # yazma yok

        hatalar = []
        logger = FlightLogger(log_dir=hedef, on_error=hatalar.append)
        sonuc = logger.start()  # istisna FIRLATMAMALI

        self.assertFalse(sonuc, "Yazilamayan klasorde start() True dondu")
        self.assertTrue(hatalar, "Hata bildirimi yapilmadi")
        self.assertIn("baslatilamadi", hatalar[0].lower())
        os.chmod(hedef, stat.S_IRWXU)

    def test_kayit_kapaliyken_satir_yazmak_guvenli(self):
        logger = FlightLogger(log_dir=self.tmp.name)
        self.assertFalse(
            logger.log_row(39.9, 32.8, 10, 3, 90, 80, "GUIDED", True)
        )

    def test_dosya_kapandiktan_sonra_yazma_kaydediciyi_kapatir(self):
        """Disk dolmasi / birim cikarilmasi taklidi."""
        hatalar = []
        logger = FlightLogger(log_dir=self.tmp.name, on_error=hatalar.append)
        logger.start()
        logger._file.close()  # alttan dosyayi kopar
        sonuc = logger.log_row(39.9, 32.8, 10, 3, 90, 80, "GUIDED", True)
        self.assertFalse(sonuc)
        self.assertTrue(hatalar)
        self.assertFalse(logger._is_active, "Kaydedici kendini kapatmadi")

    def test_ayni_hata_tekrar_tekrar_bildirilmez(self):
        hatalar = []
        logger = FlightLogger(log_dir=self.tmp.name, on_error=hatalar.append)
        logger.start()
        logger._file.close()
        for _ in range(5):
            logger.log_row(39.9, 32.8, 10, 3, 90, 80, "GUIDED", True)
        self.assertEqual(len(hatalar), 1, "Hata her satirda tekrar bildirildi")

    def test_stop_iki_kez_cagrilabilir(self):
        logger = FlightLogger(log_dir=self.tmp.name)
        logger.start()
        logger.stop()
        logger.stop()  # istisna firlatmamali


class ArmSirasindaKayitHatasiTest(unittest.TestCase):
    """Kayit acilamasa bile ARM isleme yolu tamamlanmali."""

    @classmethod
    def setUpClass(cls):
        cls.vehicle = FakeVehicle(free_udp_port())
        cls.vehicle.start()
        cls.win, cls.main_v7 = boot_gcs(cls.vehicle.port)
        assert cls.win.connected

    @classmethod
    def tearDownClass(cls):
        cls.win.flight_logger.stop()
        cls.win.voice.stop()
        cls.win.worker.stop()
        cls.vehicle.stop()

    def test_kayit_acilamasa_da_arm_arayuze_yansir(self):
        self.vehicle.armed = False
        pump(6.0, until=lambda: not self.win.is_armed)

        # Kaydediciyi yazilamaz hale getir
        self.win.flight_logger.log_dir = "/gecersiz/yol/olmayan/klasor"
        try:
            self.vehicle.armed = True
            self.assertTrue(
                pump(10.0, until=lambda: self.win.is_armed),
                "Kayit hatasi ARM islemeyi durdurdu",
            )
            # ARM'a bagli arayuz durumu da guncellenmeli
            self.assertEqual(self.win.btn_arm.text(), "DISARM")
            self.assertIsNotNone(self.win._flight_start_ts, "Ucus sayaci baslamadi")
        finally:
            self.vehicle.armed = False
            pump(10.0, until=lambda: not self.win.is_armed)


class TemizKapanmaTest(unittest.TestCase):
    def test_kapanista_worker_ve_ses_durur(self):
        vehicle = FakeVehicle(free_udp_port())
        vehicle.start()
        win, _m = boot_gcs(vehicle.port)
        self.assertTrue(win.connected)
        worker = win.worker

        win.close()
        pump(1.0)

        self.assertFalse(worker.isRunning(), "Worker thread kapanista durmadi")
        vehicle.stop()

    def test_kapanis_sonrasi_port_serbest_kalir(self):
        """Soket kapanmazsa ayni porta yeniden baglanilamaz."""
        port = free_udp_port()
        vehicle = FakeVehicle(port)
        vehicle.start()

        win1, _m = boot_gcs(port)
        self.assertTrue(win1.connected)
        win1.close()
        pump(1.0)

        win2, _m = boot_gcs(port)
        try:
            self.assertTrue(
                win2.connected, "Port serbest kalmadi, yeniden baglanilamadi"
            )
        finally:
            win2.close()
            pump(0.5)
            vehicle.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
