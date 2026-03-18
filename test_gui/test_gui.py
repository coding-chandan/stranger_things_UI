import os
import serial
import serial.tools.list_ports
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QFileDialog, QLabel, QProgressBar, QComboBox, QTextEdit
)
from PySide6.QtCore import QThread, Signal


CHUNK_SIZE = 1024  # 1 KB


class OTAWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, port, firmware_path):
        super().__init__()
        self.port = port
        self.firmware_path = firmware_path

    def run(self):
        try:
            self.log.emit("Opening serial port...")
            ser = serial.Serial(self.port, 115200, timeout=1)

        except Exception as e:
            self.finished.emit(False, f"Serial open failed: {e}")
            return

        try:
            # Read firmware
            with open(self.firmware_path, "rb") as f:
                data = f.read()

            if len(data) == 0:
                self.finished.emit(False, "Firmware file is empty.")
                ser.close()
                return

            total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE
            self.log.emit(f"Total chunks: {total_chunks}")

            for i in range(total_chunks):
                chunk = data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]

                # Retry logic
                attempts = 0
                while attempts < 3:
                    attempts += 1
                    ser.write(chunk)
                    ser.flush()

                    self.log.emit(f"Chunk {i+1}/{total_chunks}: sent, waiting for ACK...")

                    response = ser.read(1)

                    if response == b'\x06':  # ACK
                        self.log.emit("ACK received.")
                        break
                    else:
                        self.log.emit(f"No ACK, retry attempt {attempts}")

                if attempts == 3:
                    self.finished.emit(False, "OTA aborted: device did not ACK.")
                    ser.close()
                    return

                self.progress.emit(int((i + 1) / total_chunks * 100))

            ser.close()
            self.finished.emit(True, "OTA SUCCESS.")

        except Exception as e:
            self.finished.emit(False, f"OTA failed: {e}")


class OTAGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OTA Firmware Uploader")

        self.file_path = None

        layout = QVBoxLayout()

        self.port_combo = QComboBox()
        for p in serial.tools.list_ports.comports():
            self.port_combo.addItem(p.device)
        layout.addWidget(QLabel("Select USB/Serial Port:"))
        layout.addWidget(self.port_combo)

        self.file_label = QLabel("No file selected.")
        layout.addWidget(self.file_label)

        browse_btn = QPushButton("Browse Firmware")
        browse_btn.clicked.connect(self.browse_file)
        layout.addWidget(browse_btn)

        self.ota_btn = QPushButton("Start OTA")
        self.ota_btn.clicked.connect(self.start_ota)
        layout.addWidget(self.ota_btn)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self.setLayout(layout)

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Firmware File")
        if path:
            self.file_path = path
            self.file_label.setText(os.path.basename(path))

    def start_ota(self):
        if not self.file_path:
            self.log_box.append("Please select a firmware file first.")
            return

        port = self.port_combo.currentText()

        self.ota_btn.setEnabled(False)

        self.worker = OTAWorker(port, self.file_path)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.log.connect(self.log_box.append)
        self.worker.finished.connect(self.ota_result)
        self.worker.start()

    def ota_result(self, success, message):
        self.log_box.append(message)
        self.ota_btn.setEnabled(True)


if __name__ == "__main__":
    app = QApplication([])
    gui = OTAGUI()
    gui.resize(500, 400)
    gui.show()
    app.exec()
