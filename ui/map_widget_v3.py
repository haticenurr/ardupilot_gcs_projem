"""
map_widget.py (v3)
--------------------
Leaflet.js tabanli canli harita + gorev planlama widget'i.
GCS Yol Haritasi - Asama 5 + Ucus Plani + Modern Gorsel Guncelleme

v3'te duzeltilen/eklenen:
  - Waypoint tiklama hatasi duzeltildi (URL semasi artik query-string kullaniyor,
    negatif enlem/boylam degerleriyle de guvenli calisiyor).
  - Modern drone ikonu: yon (heading) gosteren donen ok + nabiz animasyonu.
  - Modern, minimalist harita temasi (CartoDB Positron).
  - Daha sik, golgeli waypoint rozetleri.
"""

import json

from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl, QUrlQuery, pyqtSignal, QTimer


LEAFLET_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map { height: 100%; margin: 0; padding: 0; background: #e8ecef; }

        .drone-wrapper {
            position: relative;
            width: 46px;
            height: 46px;
        }
        .drone-pulse {
            position: absolute;
            top: 50%; left: 50%;
            width: 46px; height: 46px;
            margin: -23px 0 0 -23px;
            border-radius: 50%;
            background: rgba(41, 128, 185, 0.25);
            animation: pulse 2s infinite ease-out;
        }
        @keyframes pulse {
            0%   { transform: scale(0.4); opacity: 0.9; }
            100% { transform: scale(1.6); opacity: 0; }
        }
        .drone-arrow {
            position: absolute;
            top: 50%; left: 50%;
            width: 30px; height: 30px;
            margin: -15px 0 0 -15px;
            transition: transform 0.25s ease-out;
        }

        .wp-badge {
            width: 26px; height: 26px;
            border-radius: 50% 50% 50% 0;
            background: linear-gradient(135deg, #f39c12, #e67e22);
            transform: rotate(45deg);
            box-shadow: 0 2px 5px rgba(0,0,0,0.4);
            border: 2px solid white;
        }
        .wp-badge-label {
            transform: rotate(-45deg);
            color: white;
            font-weight: 700;
            font-size: 12px;
            text-align: center;
            line-height: 22px;
        }

        .home-icon {
            width: 30px;
            height: 30px;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.45));
        }

        .leaflet-control-zoom a {
            border-radius: 6px !important;
        }
        .leaflet-control-layers {
            background: #1e1e2e !important;
            color: #cdd6f4 !important;
            border: 1px solid #313244 !important;
            border-radius: 8px !important;
        }
        .leaflet-control-layers-toggle {
            background-color: #1e1e2e !important;
            border-radius: 8px !important;
        }
        .leaflet-control-layers label {
            color: #cdd6f4 !important;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map', { zoomControl: true }).setView([0, 0], 2);

        // Alt katmanlar. CARTO basemap'leri artik API anahtari istiyor ve
        // anahtarsiz istekte doselemelerin uzerine "API KEY REQUIRED"
        // filigrani basiyor; bu yuzden anahtar gerektirmeyen iki kaynak
        // kullaniliyor. Uydu goruntusu drone operasyonunda arazi/engel
        // gormek icin varsayilan secildi.
        var uyduKatmani = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {
                maxZoom: 20,
                attribution: 'Goruntu &copy; Esri, Maxar, Earthstar Geographics'
            }
        );
        var sokakKatmani = L.tileLayer(
            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap katkida bulunanlar'
            }
        );

        uyduKatmani.addTo(map);
        L.control.layers(
            { 'Uydu': uyduKatmani, 'Sokak': sokakKatmani },
            null,
            { position: 'topright', collapsed: true }
        ).addTo(map);

        var droneMarker = null;
        var flightPath = L.polyline([], {color: '#2980b9', weight: 3, opacity: 0.8}).addTo(map);
        var firstUpdate = true;
        var currentHeadingDeg = 0;
        var droneTarget = { lat: null, lon: null, heading: null, path: [] };

        function buildDroneIconHtml(headingDeg) {
            return (
                '<div class="drone-wrapper">' +
                    '<div class="drone-pulse"></div>' +
                    '<div class="drone-arrow" style="transform: rotate(' + headingDeg + 'deg);">' +
                        '<svg viewBox="0 0 24 24" width="30" height="30">' +
                            '<path d="M12 2 L19 20 L12 16 L5 20 Z" ' +
                                  'fill="#2980b9" stroke="white" stroke-width="1.2" stroke-linejoin="round"/>' +
                        '</svg>' +
                    '</div>' +
                '</div>'
            );
        }

        function makeDroneIcon(headingDeg) {
            return L.divIcon({
                className: 'drone-marker-container',
                html: buildDroneIconHtml(headingDeg),
                iconSize: [46, 46],
                iconAnchor: [23, 23]
            });
        }

        function ingestDroneSamples(points, headingDeg) {
            if (points && points.length) {
                var i;
                for (i = 0; i < points.length; i++) {
                    droneTarget.path.push([points[i][0], points[i][1]]);
                    droneTarget.lat = points[i][0];
                    droneTarget.lon = points[i][1];
                }
            }
            if (headingDeg !== null && headingDeg !== undefined) {
                droneTarget.heading = headingDeg;
                currentHeadingDeg = headingDeg;
            }
        }

        function updateDronePosition(lat, lon) {
            ingestDroneSamples([[lat, lon]], null);
        }

        function updateDroneHeading(headingDeg) {
            currentHeadingDeg = headingDeg;
            droneTarget.heading = headingDeg;
            if (droneMarker === null) return;
            var el = droneMarker.getElement();
            var arrow = el ? el.querySelector('.drone-arrow') : null;
            if (arrow) {
                arrow.style.transform = 'rotate(' + headingDeg + 'deg)';
            } else {
                droneMarker.setIcon(makeDroneIcon(headingDeg));
            }
        }

        function applyDroneUpdates(points, headingDeg) {
            ingestDroneSamples(points, headingDeg);
        }

        function renderDroneFromState() {
            if (droneTarget.lat === null || droneTarget.lon === null) return;
            var pos = [droneTarget.lat, droneTarget.lon];
            if (droneMarker === null) {
                droneMarker = L.marker(pos, {
                    icon: makeDroneIcon(currentHeadingDeg),
                    zIndexOffset: 1000
                }).addTo(map);
            } else {
                droneMarker.setLatLng(pos);
            }
            if (droneTarget.heading !== null) {
                updateDroneHeading(droneTarget.heading);
            }
            flightPath.setLatLngs(droneTarget.path);
            if (firstUpdate) {
                map.setView(pos, 18);
                firstUpdate = false;
            }
        }

        setInterval(renderDroneFromState, 100);

        function clearFlightPath() {
            // Dronun ucus izini (mavi cizgi) temizler. Waypoint/gorev
            // cizgisinden (missionLine, turuncu kesikli) tamamen bagimsizdir;
            // "Gorevi Drondan Sil" gibi islemlerde eski ucus izinin
            // haritada asili kalmamasi icin ayrica cagrilmalidir.
            droneTarget.path = [];
            flightPath.setLatLngs([]);
        }

        var waypointMarkers = [];
        var missionLine = L.polyline([], {color: '#e67e22', weight: 3, dashArray: '8 6'}).addTo(map);
        var missionEditingEnabled = true;
        var homeMarker = null;
        var geofenceCircle = null;
        var fenceEditingEnabled = false;
        var fenceEditMarkers = [];
        var fenceEditLine = L.polyline([], {color: '#fab387', weight: 2, dashArray: '4 4'}).addTo(map);
        var fencePolygonLayer = null;

        function setFenceEditingMode(enabled) {
            fenceEditingEnabled = enabled;
        }

        function drawFenceEditProgress(pointsJson) {
            var points = JSON.parse(pointsJson);
            fenceEditMarkers.forEach(function(m) { map.removeLayer(m); });
            fenceEditMarkers = [];
            var latlngs = [];
            points.forEach(function(p) {
                var pos = [p[0], p[1]];
                var marker = L.circleMarker(pos, {
                    radius: 5, color: '#fab387', fillColor: '#fab387', fillOpacity: 0.9
                }).addTo(map);
                fenceEditMarkers.push(marker);
                latlngs.push(pos);
            });
            fenceEditLine.setLatLngs(latlngs);
        }

        function clearFenceEdit() {
            fenceEditMarkers.forEach(function(m) { map.removeLayer(m); });
            fenceEditMarkers = [];
            fenceEditLine.setLatLngs([]);
        }

        function drawFencePolygon(pointsJson) {
            var points = JSON.parse(pointsJson);
            var latlngs = points.map(function(p) { return [p[0], p[1]]; });
            if (fencePolygonLayer === null) {
                fencePolygonLayer = L.polygon(latlngs, {
                    color: '#f38ba8', weight: 2, fillColor: '#f38ba8', fillOpacity: 0.08
                }).addTo(map);
            } else {
                fencePolygonLayer.setLatLngs(latlngs);
            }
        }

        function clearFencePolygon() {
            if (fencePolygonLayer !== null) {
                map.removeLayer(fencePolygonLayer);
                fencePolygonLayer = null;
            }
        }
        var guidedClickEnabled = false;
        var guidedTargetMarker = null;

        function makeGuidedTargetIcon() {
            var html =
                '<div style="width:22px;height:22px;">' +
                    '<svg viewBox="0 0 24 24" width="22" height="22">' +
                        '<circle cx="12" cy="12" r="9" fill="none" stroke="#a6e3a1" stroke-width="2.5"/>' +
                        '<circle cx="12" cy="12" r="2.5" fill="#a6e3a1"/>' +
                    '</svg>' +
                '</div>';
            return L.divIcon({
                className: 'guided-target-marker',
                html: html,
                iconSize: [22, 22],
                iconAnchor: [11, 11]
            });
        }

        function showGuidedTarget(lat, lon) {
            var pos = [lat, lon];
            if (guidedTargetMarker === null) {
                guidedTargetMarker = L.marker(pos, {icon: makeGuidedTargetIcon(), zIndexOffset: 800}).addTo(map);
            } else {
                guidedTargetMarker.setLatLng(pos);
            }
        }

        function clearGuidedTarget() {
            if (guidedTargetMarker !== null) {
                map.removeLayer(guidedTargetMarker);
                guidedTargetMarker = null;
            }
        }

        function setGuidedClickMode(enabled) {
            guidedClickEnabled = enabled;
        }

        function drawGeofence(lat, lon, radiusMeters) {
            var pos = [lat, lon];
            if (geofenceCircle === null) {
                geofenceCircle = L.circle(pos, {
                    radius: radiusMeters,
                    color: '#f38ba8',
                    weight: 2,
                    fillColor: '#f38ba8',
                    fillOpacity: 0.06,
                    dashArray: '8 6'
                }).addTo(map);
            } else {
                geofenceCircle.setLatLng(pos);
                geofenceCircle.setRadius(radiusMeters);
            }
        }

        function clearGeofence() {
            if (geofenceCircle !== null) {
                map.removeLayer(geofenceCircle);
                geofenceCircle = null;
            }
        }

        function makeHomeIcon() {
            var html =
                '<div class="home-icon">' +
                    '<svg viewBox="0 0 24 24" width="30" height="30">' +
                        '<path d="M3 11.5 L12 3 L21 11.5 V21 H14 V14 H10 V21 H3 Z" ' +
                              'fill="#27ae60" stroke="white" stroke-width="1.4" stroke-linejoin="round"/>' +
                    '</svg>' +
                '</div>';
            return L.divIcon({
                className: 'home-marker',
                html: html,
                iconSize: [30, 30],
                iconAnchor: [15, 28]
            });
        }

        function updateHomePosition(lat, lon) {
            var pos = [lat, lon];
            if (homeMarker === null) {
                homeMarker = L.marker(pos, {icon: makeHomeIcon(), zIndexOffset: 400}).addTo(map);
            } else {
                homeMarker.setLatLng(pos);
            }
        }

        function makeWaypointIcon(number) {
            return L.divIcon({
                className: 'wp-marker',
                html: '<div class="wp-badge"><div class="wp-badge-label">' + number + '</div></div>',
                iconSize: [26, 26],
                iconAnchor: [13, 24]
            });
        }

        map.on('click', function(e) {
            var lat = e.latlng.lat.toFixed(7);
            var lon = e.latlng.lng.toFixed(7);
            if (fenceEditingEnabled) {
                window.location.href = "fencepoint://add?lat=" + lat + "&lon=" + lon;
                return;
            }
            if (guidedClickEnabled) {
                window.location.href = "guidedgoto://go?lat=" + lat + "&lon=" + lon;
                return;
            }
            if (!missionEditingEnabled) return;
            window.location.href = "waypoint://add?lat=" + lat + "&lon=" + lon;
        });
        function redrawWaypoints(waypointsJson) {
            var waypoints = JSON.parse(waypointsJson);

            waypointMarkers.forEach(function(m) { map.removeLayer(m); });
            waypointMarkers = [];

            var linePoints = [];
            waypoints.forEach(function(wp, idx) {
                var pos = [wp[0], wp[1]];
                var marker = L.marker(pos, {icon: makeWaypointIcon(idx + 1)}).addTo(map);
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
    waypoint_clicked = pyqtSignal(float, float)
    guided_goto_clicked = pyqtSignal(float, float)
    fence_point_clicked = pyqtSignal(float, float)
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(
            f"[JS console] {message} ({sourceID}:{lineNumber})",
            flush=True,
        )

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame):
        if url.scheme() == "waypoint":
            query = QUrlQuery(url)
            lat_str = query.queryItemValue("lat")
            lon_str = query.queryItemValue("lon")
            try:
                self.waypoint_clicked.emit(float(lat_str), float(lon_str))
            except (ValueError, TypeError) as e:
                print(f"[Harita] Waypoint koordinatlari okunamadi: {e}")
            return False
        if url.scheme() == "guidedgoto":
            query = QUrlQuery(url)
            lat_str = query.queryItemValue("lat")
            lon_str = query.queryItemValue("lon")
            try:
                self.guided_goto_clicked.emit(float(lat_str), float(lon_str))
            except (ValueError, TypeError) as e:
                print(f"[Harita] Guided-goto koordinatlari okunamadi: {e}")
            return False
        if url.scheme() == "fencepoint":
            query = QUrlQuery(url)
            lat_str = query.queryItemValue("lat")
            lon_str = query.queryItemValue("lon")
            try:
                self.fence_point_clicked.emit(float(lat_str), float(lon_str))
            except (ValueError, TypeError) as e:
                print(f"[Harita] Fence noktasi okunamadi: {e}")
            return False
        return True


class DroneMapWidget(QWebEngineView):
    waypoint_added = pyqtSignal(float, float)
    guided_goto_requested = pyqtSignal(float, float)
    fence_point_added = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self._page = _NavigationInterceptPage(self)
        self._page.waypoint_clicked.connect(self.waypoint_added)
        self._page.guided_goto_clicked.connect(self.guided_goto_requested)
        self._page.fence_point_clicked.connect(self.fence_point_added)
        self.setPage(self._page)
        self._page.setHtml(LEAFLET_HTML, QUrl("https://localhost/"))
        self._js_ready = False
        self._js_busy = False
        self._flush_scheduled = False
        self._cmd_queue = []
        self._buf_points = []
        self._buf_heading = None
        self._buf_heading_set = False
        self._page.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok):
        self._js_ready = True
        # Sayfa yeniden yuklenirse onceki runJavaScript callback'i gelmeyebilir.
        self._js_busy = False
        self._request_js_flush()

    def _request_js_flush(self):
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        QTimer.singleShot(0, self._flush_js)

    def _snapshot_drone_buffer(self):
        """Ayni event-loop turundaki position+heading cagrilarini tek JS isine birlestir."""
        if not self._buf_points and not self._buf_heading_set:
            return
        points = self._buf_points
        heading = self._buf_heading if self._buf_heading_set else None
        self._buf_points = []
        self._buf_heading = None
        self._buf_heading_set = False
        self._cmd_queue.append(("drone", points, heading))

    def _run_js(self, script):
        self._snapshot_drone_buffer()
        self._cmd_queue.append(script)
        self._request_js_flush()

    def _flush_js(self):
        self._flush_scheduled = False
        if not self._js_ready or self._js_busy:
            return
        self._snapshot_drone_buffer()
        if not self._cmd_queue:
            return
        cmd = self._cmd_queue.pop(0)
        if isinstance(cmd, tuple) and cmd[0] == "drone":
            _, points, heading = cmd
            heading_js = "null" if heading is None else json.dumps(float(heading))
            script = f"applyDroneUpdates({json.dumps(points)}, {heading_js});"
        else:
            script = cmd
        self._js_busy = True
        self.page().runJavaScript(script, self._on_js_finished)

    def _on_js_finished(self, _result):
        self._js_busy = False
        self._flush_js()

    def update_position(self, lat: float, lon: float):
        self._buf_points.append([float(lat), float(lon)])
        self._request_js_flush()

    def clear_flight_path(self):
        """Haritada birikmis mavi ucus izini (gecmis rota cizgisini) temizler.
        Waypoint/gorev cizgisinden (redraw_waypoints) bagimsizdir."""
        self._buf_points = []
        self._run_js("clearFlightPath();")

    def update_heading(self, heading_degrees: float):
        self._buf_heading = float(heading_degrees)
        self._buf_heading_set = True
        self._request_js_flush()

    def redraw_waypoints(self, waypoints):
        coords_only = [[lat, lon] for (lat, lon, alt) in waypoints]
        js_array = json.dumps(coords_only)
        escaped = js_array.replace("\\", "\\\\").replace("'", "\\'")
        self._run_js(f"redrawWaypoints('{escaped}');")

    def set_mission_editing(self, enabled: bool):
        value = "true" if enabled else "false"
        self._run_js(f"setMissionEditing({value});")

    def update_home(self, lat: float, lon: float):
        """Home konumunu yesil ev ikonuyla goster (drone marker'indan bagimsiz)."""
        self._run_js(f"updateHomePosition({lat}, {lon});")
    def update_geofence(self, lat: float, lon: float, radius_m: float):
        """Home merkezli dairesel geofence sinirini haritada gosterir."""
        self._run_js(f"drawGeofence({lat}, {lon}, {radius_m});")

    def clear_geofence(self):
        self._run_js("clearGeofence();")

    def set_guided_click_mode(self, enabled: bool):
        value = "true" if enabled else "false"
        self._run_js(f"setGuidedClickMode({value});")

    def show_guided_target(self, lat: float, lon: float):
        self._run_js(f"showGuidedTarget({lat}, {lon});")

    def clear_guided_target(self):
        self._run_js("clearGuidedTarget();")

    def set_fence_editing_mode(self, enabled: bool):
        value = "true" if enabled else "false"
        self._run_js(f"setFenceEditingMode({value});")

    def draw_fence_edit_progress(self, points):
        js_array = json.dumps(points)
        escaped = js_array.replace("\\", "\\\\").replace("'", "\\'")
        self._run_js(f"drawFenceEditProgress('{escaped}');")

    def clear_fence_edit(self):
        self._run_js("clearFenceEdit();")

    def draw_fence_polygon(self, points):
        js_array = json.dumps(points)
        escaped = js_array.replace("\\", "\\\\").replace("'", "\\'")
        self._run_js(f"drawFencePolygon('{escaped}');")

    def clear_fence_polygon(self):
        self._run_js("clearFencePolygon();")        
