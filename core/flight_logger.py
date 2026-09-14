"""
flight_logger.py
-----------------
Basit CSV tabanli ucus gunlugu kaydedici.
ARM oldugunda bir kez baslar, uygulama kapanana kadar ayni dosyaya yazmaya devam eder.
"""

import csv
import os
import re
import time
from datetime import datetime


def _sanitize_flight_name(name):
    """Kullanicinin girdigi ucus adini dosya adi icin guvenli hale getirir.
    Bos/gecersizse None doner, o zaman varsayilan (sadece tarih-saat)
    isimlendirme kullanilir."""
    if not name:
        return None
    name = name.strip()
    if not name:
        return None
    name = re.sub(r"[^A-Za-z0-9_\-ığüşöçİĞÜŞÖÇ ]", "", name)
    name = name.strip().replace(" ", "_")
    return name[:40] or None


class FlightLogger:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        self._file = None
        self._writer = None
        self._is_active = False
        self.current_filepath = None

    def start(self, custom_name=None):
        """Onceki kayit aciksa kapatir, sonra yeni CSV acar."""
        if self._is_active:
            self.stop()
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_name = _sanitize_flight_name(custom_name)
        if safe_name:
            filepath = os.path.join(self.log_dir, f"flight_{timestamp}_{safe_name}.csv")
        else:
            filepath = os.path.join(self.log_dir, f"flight_{timestamp}.csv")
        self.current_filepath = filepath
        self._file = open(filepath, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "timestamp", "lat", "lon", "alt", "groundspeed",
            "heading", "battery", "mode", "armed"
        ])
        self._is_active = True

    def log_row(self, lat, lon, alt, groundspeed, heading, battery, mode, armed):
        if not self._is_active or self._writer is None:
            return
        self._writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            lat, lon, alt, groundspeed, heading, battery, mode, armed
        ])
        self._file.flush()

    def stop(self):
        if self._file is not None:
            self._file.close()
        self._file = None
        self._writer = None
        self._is_active = False

    def get_current_filename(self):
        if self.current_filepath is None:
            return None
        return os.path.basename(self.current_filepath)
