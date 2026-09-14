"""
map_widget.py
--------------
Leaflet.js tabanli canli harita widget'i.
GCS Yol Haritasi - Asama 5

QWebEngineView icine bir HTML/JS harita (Leaflet) gomer.
Drone konumu guncellendiginde JavaScript fonksiyonunu cagirarak
haritadaki drone ikonunu hareket ettirir.
"""

from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl


LEAFLET_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map { height: 100%; margin: 0; padding: 0; }
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([0, 0], 2);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap katkida bulunanlar'
        }).addTo(map);

        var droneIcon = L.divIcon({
            className: 'drone-marker',
            html: '<div style="background:#2980b9;width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 0 4px rgba(0,0,0,0.5);"></div>',
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });

        var droneMarker = null;
        var flightPath = L.polyline([], {color: '#2980b9', weight: 2}).addTo(map);
        var pathPoints = [];
        var firstUpdate = true;

        function updateDronePosition(lat, lon) {
            var pos = [lat, lon];

            if (droneMarker === null) {
                droneMarker = L.marker(pos, {icon: droneIcon}).addTo(map);
            } else {
                droneMarker.setLatLng(pos);
            }

            pathPoints.push(pos);
            flightPath.setLatLngs(pathPoints);

            if (firstUpdate) {
                map.setView(pos, 18);
                firstUpdate = false;
            }
        }
    </script>
</body>
</html>
"""


class DroneMapWidget(QWebEngineView):
    def __init__(self):
        super().__init__()
        self.setHtml(LEAFLET_HTML, QUrl("https://localhost/"))

    def update_position(self, lat: float, lon: float):
        js_code = f"updateDronePosition({lat}, {lon});"
        self.page().runJavaScript(js_code)
