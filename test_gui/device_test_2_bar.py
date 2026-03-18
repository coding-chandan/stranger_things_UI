"""
Leshuffler Firmware Update - Final

Features:
- Indeterminate (live/animated) progress bar while OTA runs
- Proper chunked OTA over serial (1024 bytes)
- ACK/NACK handling, retries, abort after 3 consecutive chunk failures
- File selection (only .sfb) shows filename only
- Popups for success/failure/aborted/errors
- Worker thread to keep UI responsive
- Minor robustness fixes (no duplicate starts, safe percent updates)
"""

import sys
import os
import time
import threading
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QProgressBar, QMessageBox, QHBoxLayout, QDialog, QFormLayout, QLineEdit, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QObject

# try to import pyserial (used only for real-serial mode)
try:
    import serial
except Exception:
    serial = None

# --------------------------- Configurable Defaults ---------------------------
CHUNK_SIZE = 1024
ACK_BYTE = b"\x06"
NACK_BYTE = b"\x15"
MAX_RETRIES = 3
SERIAL_TIMEOUT = 2.0

# Default serial settings (used unless changed in Advanced settings)
DEFAULT_PORT = "COM3"          # Windows example
# DEFAULT_PORT = "/dev/ttyUSB0"  # Linux example
DEFAULT_BAUD = 115200
# ---------------------------------------------------------------------------


class OTAResult:
    SUCCESS = "success"
    FAILURE = "failure"
    ABORTED = "aborted"


class OTAProgressSignals(QObject):
    percent = Signal(int)
    bytes_sent = Signal(int)
    finished = Signal(str)
    enable_ui = Signal(bool)
    error = Signal(str)


class OTAWorker(threading.Thread):
    """Worker thread that performs the OTA transfer so the UI stays responsive."""

    def __init__(self, firmware_path: str, port: str, baud: int, signals: OTAProgressSignals):
        super().__init__()
        self.firmware_path = firmware_path
        self.port = port
        self.baud = baud
        self.signals = signals
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _open_serial(self) -> Tuple[bool, Optional[object], str]:
        if serial is None:
            return False, None, "pyserial not installed/available"
        try:
            ser = serial.Serial(self.port, self.baud, timeout=SERIAL_TIMEOUT)
            return True, ser, ""
        except Exception as e:
            return False, None, str(e)

    def run(self):
        # disable UI
        self.signals.enable_ui.emit(False)
        try:
            # Validate firmware
            if not Path(self.firmware_path).is_file():
                self.signals.error.emit("Firmware file not found")
                self.signals.finished.emit(OTAResult.FAILURE)
                self.signals.enable_ui.emit(True)
                return

            total_bytes = os.path.getsize(self.firmware_path)
            if total_bytes == 0:
                self.signals.error.emit("Firmware file is empty")
                self.signals.finished.emit(OTAResult.FAILURE)
                self.signals.enable_ui.emit(True)
                return

            ok, ser, err = self._open_serial()
            if not ok:
                self.signals.error.emit(f"Failed to open serial port: {err}")
                self.signals.finished.emit(OTAResult.FAILURE)
                self.signals.enable_ui.emit(True)
                return

            bytes_sent = 0
            consecutive_chunk_failures = 0

            with open(self.firmware_path, "rb") as f:
                while True:
                    if self._stop.is_set():
                        try:
                            ser.close()
                        except Exception:
                            pass
                        self.signals.finished.emit(OTAResult.ABORTED)
                        self.signals.enable_ui.emit(True)
                        return

                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    chunk_len = len(chunk)
                    success = False

                    for attempt in range(1, MAX_RETRIES + 1):
                        try:
                            ser.write(chunk)
                            ser.flush()
                        except Exception as e:
                            # write failed, continue to retry
                            self.signals.error.emit(f"Write error on attempt {attempt}: {e}")
                            time.sleep(0.05)
                            continue

                        # Wait for response
                        resp = ser.read(1)

                        if resp == ACK_BYTE:
                            # success for this chunk
                            success = True
                            bytes_sent += chunk_len
                            percent = int((bytes_sent / total_bytes) * 100) if total_bytes else 100
                            percent = max(0, min(100, percent))
                            # emit progress
                            self.signals.bytes_sent.emit(bytes_sent)
                            self.signals.percent.emit(percent)
                            consecutive_chunk_failures = 0
                            break
                        elif resp == NACK_BYTE:
                            # explicit NACK — will retry
                            self.signals.error.emit(f"NACK received for chunk (attempt {attempt})")
                            time.sleep(0.05)
                            continue
                        else:
                            # timeout or unexpected response — treat as retryable
                            if resp == b"" or resp is None:
                                self.signals.error.emit(f"No response (attempt {attempt})")
                            else:
                                self.signals.error.emit(f"Unexpected response {resp!r} (attempt {attempt})")
                            time.sleep(0.05)
                            continue

                    if not success:
                        consecutive_chunk_failures += 1
                        if consecutive_chunk_failures >= 3:
                            try:
                                ser.close()
                            except Exception:
                                pass
                            self.signals.error.emit("Maximum consecutive chunk failures reached — aborting")
                            self.signals.finished.emit(OTAResult.FAILURE)
                            self.signals.enable_ui.emit(True)
                            return

            try:
                ser.close()
            except Exception:
                pass

            # finalize
            self.signals.percent.emit(100)
            self.signals.bytes_sent.emit(total_bytes)
            self.signals.finished.emit(OTAResult.SUCCESS)

        except Exception as e:
            self.signals.error.emit(f"Unexpected error in OTA worker: {e}")
            self.signals.finished.emit(OTAResult.FAILURE)
        finally:
            self.signals.enable_ui.emit(True)


class AdvancedSettingsDialog(QDialog):
    def __init__(self, parent=None, port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setModal(True)
        self.port = port
        self.baud = baud
        self._build()

    def _build(self):
        layout = QFormLayout()
        self.port_edit = QLineEdit(self.port)
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(300, 1000000)
        self.baud_spin.setValue(self.baud)

        layout.addRow("Serial Port:", self.port_edit)
        layout.addRow("Baudrate:", self.baud_spin)

        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)

        self.setLayout(layout)

    def _on_ok(self):
        self.port = self.port_edit.text().strip()
        self.baud = int(self.baud_spin.value())
        self.accept()

    def get_values(self) -> Tuple[str, int]:
        return self.port, self.baud


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Leshuffler Firmware Update")
        self.setMinimumSize(520, 260)

        self.signals = OTAProgressSignals()
        self.worker: Optional[OTAWorker] = None

        self._serial_port = DEFAULT_PORT
        self._baud = DEFAULT_BAUD

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout()

        lbl_title = QLabel("<h2>Leshuffler Firmware Update</h2>")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)

        file_layout = QHBoxLayout()
        self.lbl_file = QLabel("No file selected")
        btn_select = QPushButton("Select .sfb File")
        btn_select.clicked.connect(self._on_select_file)
        file_layout.addWidget(self.lbl_file)
        file_layout.addWidget(btn_select)
        layout.addLayout(file_layout)

        action_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start OTA")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_advanced = QPushButton("Advanced")

        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_advanced.clicked.connect(self._on_advanced)

        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_cancel)
        action_layout.addWidget(self.btn_advanced)
        layout.addLayout(action_layout)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        self.setLayout(layout)

    def _connect_signals(self):
        self.signals.percent.connect(self._set_percent)
        self.signals.bytes_sent.connect(self._set_bytes_sent)
        self.signals.finished.connect(self._on_finished)
        self.signals.enable_ui.connect(self._set_ui_enabled)
        self.signals.error.connect(self._on_error)

    def _on_select_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select firmware (.sfb)", os.getcwd(), "SFB Files (*.sfb)")
        if not fname:
            return
        if not fname.lower().endswith('.sfb'):
            QMessageBox.warning(self, "Invalid file", "Please select a .sfb firmware file.")
            return

        self._firmware_path = fname
        self.lbl_file.setText(Path(fname).name)

    def _on_advanced(self):
        dlg = AdvancedSettingsDialog(self, port=self._serial_port, baud=self._baud)
        # disable advanced while OTA is running
        if dlg.exec() == QDialog.Accepted:
            port, baud = dlg.get_values()
            self._serial_port = port
            self._baud = baud
            QMessageBox.information(self, "Settings Saved", f"Port: {port}\nBaud: {baud}")

    def _on_start(self):
        if not hasattr(self, '_firmware_path'):
            QMessageBox.warning(self, "No file", "Please select a .sfb file before starting.")
            return

        confirm = QMessageBox.question(
            self,
            "Start OTA",
            f"Start firmware update with file: {self.lbl_file.text()}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        # disable controls
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_advanced.setEnabled(False)
        self.lbl_status.setText("Connecting to device...")

        # === Show indeterminate (live) animated progress bar ===
        # setting range to 0,0 makes the progress bar show an animated busy indicator
        self.progress.setRange(0, 0)

        # start worker
        self.worker = OTAWorker(self._firmware_path, self._serial_port, self._baud, self.signals)
        self.worker.start()

    def _on_cancel(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("Cancelling...")
            self.btn_cancel.setEnabled(False)

    def _set_percent(self, p: int):
        # Only update percent when progress bar is determinate (range != 0)
        if self.progress.maximum() != 0:
            self.progress.setValue(p)

    def _set_bytes_sent(self, b: int):
        total = os.path.getsize(self._firmware_path) if hasattr(self, '_firmware_path') else 0
        self.lbl_status.setText(f"{b} / {total} bytes sent")

    def _on_finished(self, result: str):
        # stop animation and show determinate bar
        self.progress.setRange(0, 100)

        # re-enable controls
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_advanced.setEnabled(True)

        if result == OTAResult.SUCCESS:
            self.progress.setValue(100)
            QMessageBox.information(self, "OTA Complete", "Firmware update completed successfully.")
            self.lbl_status.setText("Update completed")
        elif result == OTAResult.ABORTED:
            self.progress.setValue(0)
            QMessageBox.warning(self, "OTA Aborted", "OTA was cancelled by the user.")
            self.lbl_status.setText("OTA aborted")
        else:
            self.progress.setValue(0)
            QMessageBox.critical(self, "OTA Failed", "Firmware update failed. Please try again.")
            self.lbl_status.setText("OTA failed")

    def _set_ui_enabled(self, enabled: bool):
        self.btn_start.setEnabled(enabled)
        self.btn_advanced.setEnabled(enabled)

    def _on_error(self, msg: str):
        # Show non-intrusive popup for errors during OTA attempts
        QMessageBox.warning(self, "OTA Notice", msg)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
