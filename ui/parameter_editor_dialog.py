"""
parameter_editor_dialog.py
-----------------------------
FC'deki tum parametreleri listeleyen, arattiran ve tek tek duzenletip
yazdiran (PARAM_SET) pencere. Non-modal calisir: acikken de arka planda
telemetri akmaya devam eder, MainWindow her PARAM_VALUE mesajini
on_param_received() ile bu pencereye iletir.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal


class ParameterEditorDialog(QDialog):
    request_download = pyqtSignal()
    apply_param = pyqtSignal(str, float, int)  # name, value, param_type

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parametre Listesi")
        self.setMinimumSize(560, 620)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLineEdit {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 8px; padding: 6px 10px;
            }
            QTableWidget {
                background-color: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 8px;
                gridline-color: #313244;
            }
            QHeaderView::section {
                background-color: #313244; color: #89dceb;
                padding: 6px; border: none; font-weight: 700;
            }
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: none; border-radius: 6px; padding: 6px 10px; font-weight: 700;
            }
            QPushButton:hover { background-color: #45475a; }
        """)

        self._row_to_name = {}
        self._name_to_row = {}
        self._param_types = {}

        layout = QVBoxLayout(self)

        title = QLabel("Parametre Listesi")
        title.setStyleSheet("color: #89dceb; font-size: 14px; font-weight: 800;")
        layout.addWidget(title)

        top_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Parametre ara (orn. FENCE, RTL, BATT)...")
        self.search_box.textChanged.connect(self._on_search_changed)
        top_row.addWidget(self.search_box, 1)

        self.refresh_btn = QPushButton("FC'den Yeniden Indir")
        self.refresh_btn.clicked.connect(self.request_download.emit)
        top_row.addWidget(self.refresh_btn)
        layout.addLayout(top_row)

        self.progress_label = QLabel("Indirilmedi. 'FC'den Yeniden Indir' ile baslat.")
        self.progress_label.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.progress_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Parametre", "Deger", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def on_param_received(self, data: dict):
        """
        Satirlar PARAMETRE ADINA gore takip edilir (param_index'e gore
        DEGIL). Neden: bir parametre hem tek tek (PARAM_REQUEST_READ,
        orn. Failsafe panelinden) hem de toplu listede (PARAM_REQUEST_LIST)
        gelebilir; index tabanli yerlestirme bu iki kaynagin ayni satira
        farkli anlarda yazip birbirini EZMESINE (bir parametrenin gorunmez
        olmasina) sebep olabiliyordu. Ad tabanli sozluk bu riski tamamen
        ortadan kaldirir - ayni ad her zaman ayni satira gider, coklu
        mesaj gelmesi sorun yaratmaz.
        """
        name = data.get("param_id", "")
        value = data.get("value", 0.0)
        index = data.get("param_index")
        count = data.get("param_count")
        param_type = data.get("param_type", 9)

        if name in self._name_to_row:
            row = self._name_to_row[name]
        else:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._name_to_row[name] = row

        self._row_to_name[row] = name
        self._param_types[name] = param_type

        name_item = QTableWidgetItem(name)
        name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(row, 0, name_item)

        value_item = QTableWidgetItem(f"{value:.6g}")
        value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        self.table.setItem(row, 1, value_item)

        apply_btn = QPushButton("Uygula")
        apply_btn.clicked.connect(lambda _checked=False, r=row: self._on_apply_clicked(r))
        self.table.setCellWidget(row, 2, apply_btn)

        if count:
            downloaded = len(self._name_to_row)
            if downloaded >= count:
                self.progress_label.setText(f"Tamamlandi: {downloaded} parametre indirildi")
            else:
                self.progress_label.setText(f"{downloaded} / {count} parametre indirildi")

        self.table.setRowHidden(row, not self._row_matches_filter(row))

    def _row_matches_filter(self, row: int) -> bool:
        text = self.search_box.text().strip().lower()
        if not text:
            return True
        name = self._row_to_name.get(row, "")
        return text in name.lower()

    def _on_search_changed(self, _text):
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, not self._row_matches_filter(row))

    def _on_apply_clicked(self, row: int):
        name = self._row_to_name.get(row)
        if not name:
            return
        value_item = self.table.item(row, 1)
        if value_item is None:
            return
        try:
            new_value = float(value_item.text())
        except ValueError:
            QMessageBox.warning(self, "Gecersiz Deger", f"'{value_item.text()}' sayiya cevrilemedi.")
            return

        reply = QMessageBox.question(
            self,
            "Parametre Yaz",
            f"{name} = {new_value}\n\nBu degeri FC'ye yazmak istediginizden emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        param_type = self._param_types.get(name, 9)
        self.apply_param.emit(name, new_value, param_type)
