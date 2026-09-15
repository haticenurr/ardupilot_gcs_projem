"""
test_connection_dialog.py
--------------------------
Baglanti Ayarlari penceresi, mevcut baglanti adresini dogru sayfaya
yansitmali.

Regresyon: eski kod yalnizca "udp" onekine bakiyordu, bu yuzden bir TCP
adresi (SITL ikili dosyasina dogrudan baglanti, tcp:127.0.0.1:5760)
"seri port" sayfasina dusuyordu.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui_harness import qt_app

from ui.connection_dialog import ConnectionDialog

AG_SAYFASI = 0
SERI_SAYFA = 1


class ConnectionDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def _dialog(self, adres):
        d = ConnectionDialog(adres)
        self.addCleanup(d.deleteLater)
        return d

    def test_udp_adresi_ag_sayfasini_secer(self):
        d = self._dialog("udp:127.0.0.1:14550")
        self.assertEqual(d.stack.currentIndex(), AG_SAYFASI)
        self.assertEqual(d.udp_combo.currentText(), "udp:127.0.0.1:14550")

    def test_tcp_adresi_ag_sayfasini_secer(self):
        """Asil regresyon: tcp: adresi seri port sanilmamali."""
        d = self._dialog("tcp:127.0.0.1:5760")
        self.assertEqual(
            d.stack.currentIndex(), AG_SAYFASI,
            "TCP adresi seri port sayfasina dustu",
        )
        self.assertEqual(d.udp_combo.currentText(), "tcp:127.0.0.1:5760")

    def test_seri_port_seri_sayfayi_secer(self):
        d = self._dialog("/dev/ttyUSB0,57600")
        self.assertEqual(d.stack.currentIndex(), SERI_SAYFA)

    def test_sitl_tcp_adresi_hazir_secenek_olarak_sunulur(self):
        d = self._dialog("udp:127.0.0.1:14550")
        secenekler = [d.udp_combo.itemText(i) for i in range(d.udp_combo.count())]
        self.assertIn("tcp:127.0.0.1:5760", secenekler)

    def test_ag_adresi_oldugu_gibi_dondurulur(self):
        d = self._dialog("udp:127.0.0.1:14550")
        d.udp_combo.setCurrentText("tcp:192.168.1.50:5760")
        d._on_connect_clicked()
        self.assertEqual(d.get_connection_string(), "tcp:192.168.1.50:5760")


if __name__ == "__main__":
    unittest.main(verbosity=2)
