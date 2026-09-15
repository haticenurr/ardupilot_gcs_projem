"""
test_map_widget.py
-------------------
Harita alt katmanlari.

Regresyon: CARTO basemap'leri API anahtari istemeye basladi ve anahtarsiz
isteklerde doseme gorsellerinin uzerine "API KEY REQUIRED" filigrani
basiliyor. Katmanlar anahtar gerektirmeyen kaynaklardan gelmelidir.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.map_widget_v3 import LEAFLET_HTML


class MapTileTest(unittest.TestCase):
    def test_carto_kullanilmiyor(self):
        """CARTO anahtarsiz kullanimda filigran basiyor."""
        self.assertNotIn("cartocdn", LEAFLET_HTML)

    def test_uydu_katmani_var(self):
        self.assertIn("World_Imagery", LEAFLET_HTML)

    def test_sokak_katmani_var(self):
        self.assertIn("tile.openstreetmap.org", LEAFLET_HTML)

    def test_katman_secici_var(self):
        self.assertIn("L.control.layers", LEAFLET_HTML)
        self.assertIn("Uydu", LEAFLET_HTML)
        self.assertIn("Sokak", LEAFLET_HTML)

    def test_katmanlar_anahtar_istemiyor(self):
        """Doseme adreslerinde apikey/access_token parametresi olmamali."""
        for anahtar in ("apikey", "api_key", "access_token", "YOUR_KEY"):
            self.assertNotIn(anahtar, LEAFLET_HTML.lower())

    def test_kaynak_gosterimi_korunuyor(self):
        """OSM ve Esri lisanslari kaynak gosterimi zorunlu kilar."""
        self.assertIn("OpenStreetMap", LEAFLET_HTML)
        self.assertIn("Esri", LEAFLET_HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
