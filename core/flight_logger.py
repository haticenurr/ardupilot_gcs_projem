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
    """CSV ucus kaydi.

    Kayit tutmak ucusun KENDISINDEN daha az onemlidir: disk dolu, klasor
    salt-okunur ya da USB cikarilmis olabilir. Bu durumlarda kaydedici
    sessizce devre disi kalir ve `on_error` ile durumu bildirir; arayuzun
    geri kalani (ARM rozetleri, ucus sayaci, butonlar) calismaya devam
    eder.
    """

    def __init__(self, log_dir="logs", on_error=None):
        self.log_dir = log_dir
        self._file = None
        self._writer = None
        self._is_active = False
        self.current_filepath = None
        self._on_error = on_error
        self._error_reported = False

    def _hata(self, mesaj):
        print(f"[FlightLogger] {mesaj}")
        if self._on_error and not self._error_reported:
            self._error_reported = True
            try:
                self._on_error(mesaj)
            except Exception:
                pass

    def start(self, custom_name=None):
        """Onceki kayit aciksa kapatir, sonra yeni CSV acar.

        Dosya acilamazsa ISTISNA FIRLATMAZ: False doner ve `on_error`
        cagrilir. Bu cagri ARM isleme yolunun ortasindan yapildigi icin,
        buradan cikan bir istisna rozetlerin ve ucus sayacinin hic
        guncellenmemesine yol aciyordu."""
        if self._is_active:
            self.stop()
        self._error_reported = False
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_name = _sanitize_flight_name(custom_name)
        if safe_name:
            filepath = os.path.join(self.log_dir, f"flight_{timestamp}_{safe_name}.csv")
        else:
            filepath = os.path.join(self.log_dir, f"flight_{timestamp}.csv")
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            self._file = open(filepath, "w", newline="")
            self._writer = csv.writer(self._file)
            self._writer.writerow([
                "timestamp", "lat", "lon", "alt", "groundspeed",
                "heading", "battery", "mode", "armed"
            ])
        except OSError as e:
            self._file = None
            self._writer = None
            self._is_active = False
            self.current_filepath = None
            self._hata(f"Ucus kaydi baslatilamadi ({filepath}): {e}")
            return False
        self.current_filepath = filepath
        self._is_active = True
        return True

    def log_row(self, lat, lon, alt, groundspeed, heading, battery, mode, armed):
        """Tek satir yazar. Disk dolarsa veya birim cikarilirsa kaydedici
        kendini kapatir; ucus telemetrisi akmaya devam eder."""
        if not self._is_active or self._writer is None:
            return False
        try:
            self._writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                lat, lon, alt, groundspeed, heading, battery, mode, armed
            ])
            self._file.flush()
        except (OSError, ValueError) as e:
            self._is_active = False
            self._hata(f"Ucus kaydi yazilamadi, kayit durduruldu: {e}")
            return False
        return True

    def stop(self):
        if self._file is not None:
            try:
                self._file.close()
            except OSError as e:
                print(f"[FlightLogger] Dosya kapatilamadi: {e}")
        self._file = None
        self._writer = None
        self._is_active = False

    def get_current_filename(self):
        if self.current_filepath is None:
            return None
        return os.path.basename(self.current_filepath)
