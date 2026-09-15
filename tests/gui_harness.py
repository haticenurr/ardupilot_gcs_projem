"""
gui_harness.py
---------------
GUI testleri icin ortak altyapi: Qt'yi ekransiz (offscreen) baslatir,
MainWindow'u sahte araca baglar ve olay dongusunu testten surer.
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

_app = None


def qt_app():
    """Surec basina tek QApplication dondurur."""
    global _app
    if _app is None:
        # QtWebEngine (harita) QApplication'dan ONCE bu bayragi ister.
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        _app = QApplication.instance() or QApplication([])
    return _app


def pump(seconds, until=None):
    """Qt olay dongusunu isletir. `until` verilirse kosul saglaninca erken
    doner; worker thread'inden gelen sinyaller ancak boyle islenir."""
    app = qt_app()
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if until is not None and until():
            app.processEvents()
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(until()) if until is not None else True


def boot_gcs(port, connect_timeout=10.0, voice_backend=None):
    """MainWindow'u verilen porttaki sahte araca baglar.

    voice_backend: sesli uyarilarin arka ucu. Varsayilan olarak hicbir sey
    yapmayan bir fonksiyondur — testler sirasinda bilgisayarin gercekten
    konusmasini onler. Ses testleri buraya kaydedici bir fonksiyon verir.
    """
    qt_app()
    import main_v7
    from core.voice_alerts import VoiceAlerts

    main_v7.UDP_ENDPOINT = f"udpin:127.0.0.1:{port}"
    win = main_v7.MainWindow()

    win.voice.stop()
    win.voice = VoiceAlerts(
        enabled=True, backend=voice_backend or (lambda metin: None)
    )
    win._refresh_voice_button()

    pump(connect_timeout, until=lambda: win.connected)
    return win, main_v7
