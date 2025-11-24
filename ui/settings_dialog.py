from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QDialogButtonBox, QLineEdit

class SettingsDialog(QDialog):
    def __init__(self, scrape_value: int, scrape_unit_index: int, cookie_string: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        layout = QVBoxLayout(self)
        lbl = QLabel("Hangi periyotta çekmek istiyorsunuz?")
        layout.addWidget(lbl)
        row = QHBoxLayout()
        self.spin = QSpinBox()
        self.spin.setRange(1, 100000)
        self.spin.setValue(scrape_value)
        self.unit = QComboBox()
        self.unit.addItems(["Dakika", "Saat"])
        self.unit.setCurrentIndex(0 if scrape_unit_index == 0 else 1)
        row.addWidget(self.spin)
        row.addWidget(self.unit)
        layout.addLayout(row)
        clbl = QLabel("Cookie String")
        layout.addWidget(clbl)
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setText("" if cookie_string is None else str(cookie_string))
        layout.addWidget(self.cookie_edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def get_values(self):
        return self.spin.value(), self.unit.currentIndex(), self.cookie_edit.text().strip() or None