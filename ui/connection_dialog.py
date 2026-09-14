"""
connection_dialog.py
---------------------
Baglanti Ayarlari penceresi.
SITL/UDP ile gercek donanim (seri port) arasinda secim yapmayi saglar.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QStackedWidget, QWidget
)

try:
    from serial.tools import list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


class ConnectionDialog(QDialog):
    def __init__(self, current_connection_string: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Baglanti Ayarlari")
        self.setMinimumWidth(360)

        self._result_connection_string = None

        layout = QVBoxLayout(self)

        # --- Baglanti tipi secici ---
        layout.addWidget(QLabel("Baglanti Tipi:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("SITL / UDP (Simulasyon)", "udp")
        self.type_combo.addItem("Gercek Donanim / Seri Port", "serial")
        layout.addWidget(self.type_combo)

        # --- UDP sayfasi ---
        self.udp_page = QWidget()
        udp_layout = QVBoxLayout(self.udp_page)
        udp_layout.addWidget(QLabel("UDP Adresi (ornek: udp:127.0.0.1:14550):"))
        self.udp_combo = QComboBox()
        self.udp_combo.setEditable(True)
        self.udp_combo.addItem("udp:127.0.0.1:14550")
        udp_layout.addWidget(self.udp_combo)

        # --- Seri port sayfasi ---
        self.serial_page = QWidget()
        serial_layout = QVBoxLayout(self.serial_page)
        serial_layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self._refresh_ports()
        serial_layout.addWidget(self.port_combo)

        refresh_btn = QPushButton("Portlari Yenile")
        refresh_btn.clicked.connect(self._refresh_ports)
        serial_layout.addWidget(refresh_btn)

        serial_layout.addWidget(QLabel("Baud Rate:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["57600", "115200", "921600", "9600"])
        serial_layout.addWidget(self.baud_combo)

        # --- Sayfalari yigina ekle ---
        self.stack = QStackedWidget()
        self.stack.addWidget(self.udp_page)
        self.stack.addWidget(self.serial_page)
        layout.addWidget(self.stack)

        self.type_combo.currentIndexChanged.connect(
            lambda idx: self.stack.setCurrentIndex(idx)
        )

        # --- Mevcut baglantiyi baslangic degeri olarak yansit ---
        if current_connection_string and not current_connection_string.startswith("udp"):
            self.type_combo.setCurrentIndex(1)
            self.stack.setCurrentIndex(1)
        elif current_connection_string:
            self.udp_combo.setCurrentText(current_connection_string)

        # --- Butonlar ---
        button_row = QHBoxLayout()
        cancel_btn = QPushButton("Iptal")
        cancel_btn.clicked.connect(self.reject)
        connect_btn = QPushButton("Baglan")
        connect_btn.setDefault(True)
        connect_btn.clicked.connect(self._on_connect_clicked)
        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(connect_btn)
        layout.addLayout(button_row)

    def _refresh_ports(self):
        self.port_combo.clear()
        if not PYSERIAL_AVAILABLE:
            self.port_combo.addItem("pyserial kurulu degil")
            return
        ports = list(list_ports.comports())
        if not ports:
            self.port_combo.addItem("Port bulunamadi")
            return
        for p in ports:
            self.port_combo.addItem(f"{p.device} ({p.description})", p.device)

    def _on_connect_clicked(self):
        if self.type_combo.currentData() == "udp":
            self._result_connection_string = self.udp_combo.currentText().strip()
        else:
            port = self.port_combo.currentData()
            if port is None:
                port = self.port_combo.currentText()
            baud = self.baud_combo.currentText().strip()
            self._result_connection_string = f"{port},{baud}"
        self.accept()

    def get_connection_string(self):
        return self._result_connection_string
