"""
map_widget.py
--------------
Leaflet.js tabanli canli harita + gorev planlama (mission planning) widget'i.
GCS Yol Haritasi - Asama 5 + Ucus Plani ozelligi
"""

from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl, pyqtSignal


LEAFLET_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map { height: 100%; margin: 0; padding: 0; }
        .wp-icon {
            background: #e67e22;
            color: white;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
            border: 2px solid white;
            box-shadow: 0 0 4px rgba(0,0,0,0.5);
        }
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

        var waypointMarkers = [];
        var missionLine = L.polyline([], {color: '#e67e22', weight: 3, dashArray: '6 6'}).addTo(map);
        var missionEditingEnabled = true;

        function makeWaypointIcon(number) {
            return L.divIcon({
                className: 'wp-marker',
                html: '<div class="wp-icon">' + number + '</div>',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
        }

        map.on('click', function(e) {
            if (!missionEditingEnabled) return;
            var lat = e.latlng.lat.toFixed(7);
            var lon = e.latlng.lng.toFixed(7);
            window.location.href = "waypoint://" + lat + "," + lon;
        });

        function redrawWaypoints(waypointsJson) {
            var waypoints = JSON.parse(waypointsJson);

            waypointMarkers.forEach(function(m) { map.removeLayer(m); });
            waypointMarkers = [];

            var linePoints = [];
            waypoints.forEach(function(wp, idx) {
                var pos = [wp[0], wp[1]];
                var marker = L.marker(pos, {icon: makeWaypointIcon(idx + 1), draggable: false}).addTo(map);
                waypointMarkers.push(marker);
                linePoints.push(pos);
            });
            missionLine.setLatLngs(linePoints);
        }

        function setMissionEditing(enabled) {
            missionEditingEnabled = enabled;
        }
    </script>
</body>
</html>
"""


class _NavigationInterceptPage(QWebEnginePage):
    """
    Haritadaki tiklama olaylarini yakalamak icin ozel bir sayfa sinifi.
    """
    waypoint_clicked = pyqtSignal(float, float)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame):
        if url.scheme() == "waypoint":
            coords_text = (url.host() + url.path()).strip("/")
            try:
                lat_str, lon_str = coords_text.split(",")
                self.waypoint_clicked.emit(float(lat_str), float(lon_str))
            except Exception as e:
                print(f"[Harita] Waypoint URL ayristirilamadi: {e}")
            return False
        return True


class DroneMapWidget(QWebEngineView):
    waypoint_added = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self._page = _NavigationInterceptPage(self)
        self._page.waypoint_clicked.connect(self.waypoint_added)
        self.setPage(self._page)
        self._page.setHtml(LEAFLET_HTML, QUrl("https://localhost/"))

    def update_position(self, lat: float, lon: float):
        self.page().runJavaScript(f"updateDronePosition({lat}, {lon});")

    def redraw_waypoints(self, waypoints):
        import json
        coords_only = [[lat, lon] for (lat, lon, alt) in waypoints]
        js_array = json.dumps(coords_only)
        escaped = js_array.replace("\\", "\\\\").replace("'", "\\'")
        self.page().runJavaScript(f"redrawWaypoints('{escaped}');")

    def set_mission_editing(self, enabled: bool):
        value = "true" if enabled else "false"
        self.page().runJavaScript(f"setMissionEditing({value});")
