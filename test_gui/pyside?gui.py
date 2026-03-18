"""
Leshuffler Firmware OTA Updater
A modular GUI application for performing Over-The-Air firmware updates via serial interface
Built with PySide6
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QComboBox,
    QFileDialog, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
import serial
import serial.tools.list_ports
import sys
import time
from pathlib import Path
from typing import Optional
from enum import Enum


class OTAResponse(Enum):
    """Enumeration for OTA response types"""
    ACK = "ACK"
    NACK = "NACK"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class SerialCommunicator:
    """Handles serial communication with the device"""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: int = 5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None
    
    def connect(self) -> bool:
        """Establish serial connection"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
    
    def send_chunk(self, chunk: bytes) -> bool:
        """Send a chunk of data"""
        try:
            self.serial_conn.write(chunk)
            return True
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def wait_for_response(self) -> OTAResponse:
        """Wait for and parse device response"""
        try:
            response = self.serial_conn.readline().decode('utf-8').strip()
            if "ACK" in response:
                return OTAResponse.ACK
            elif "NACK" in response:
                return OTAResponse.NACK
            else:
                return OTAResponse.ERROR
        except serial.SerialTimeoutException:
            return OTAResponse.TIMEOUT
        except Exception as e:
            print(f"Response error: {e}")
            return OTAResponse.ERROR


class FirmwareUpdateWorker(QThread):
    """Worker thread for performing firmware updates"""
    
    # Signals for communication with GUI
    progress_updated = Signal(int, int)  # current, total
    status_updated = Signal(str)
    update_completed = Signal(bool)  # success
    
    CHUNK_SIZE = 1024  # 1 KB
    MAX_RETRIES = 3
    
    def __init__(self, port: str, firmware_path: str):
        super().__init__()
        self.port = port
        self.firmware_path = firmware_path
        self.communicator = None
        self.should_stop = False
    
    def stop(self):
        """Stop the update process"""
        self.should_stop = True
    
    def load_firmware(self, filepath: str) -> Optional[bytes]:
        """Load firmware file into memory"""
        try:
            with open(filepath, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"File load error: {e}")
            return None
    
    def run(self):
        """Main thread execution"""
        success = False
        
        try:
            # Initialize communicator
            self.status_updated.emit(f"Connecting to {self.port}...")
            self.communicator = SerialCommunicator(self.port)
            
            if not self.communicator.connect():
                self.status_updated.emit("Failed to connect to device")
                self.update_completed.emit(False)
                return
            
            self.status_updated.emit("Connected successfully")
            
            # Load firmware
            self.status_updated.emit("Loading firmware file...")
            firmware_data = self.load_firmware(self.firmware_path)
            
            if not firmware_data:
                self.status_updated.emit("Failed to load firmware file")
                self.update_completed.emit(False)
                return
            
            self.status_updated.emit(f"Firmware loaded: {len(firmware_data)} bytes")
            
            # Perform update
            success = self.update_firmware(firmware_data)
            
        except Exception as e:
            self.status_updated.emit(f"Unexpected error: {str(e)}")
            success = False
        
        finally:
            if self.communicator:
                self.communicator.disconnect()
            self.update_completed.emit(success)
    
    def update_firmware(self, firmware_data: bytes) -> bool:
        """Perform the OTA update process"""
        total_chunks = (len(firmware_data) + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
        
        self.status_updated.emit(f"Starting OTA update... ({total_chunks} chunks)")
        
        for chunk_num in range(total_chunks):
            if self.should_stop:
                self.status_updated.emit("Update cancelled by user")
                return False
            
            start_idx = chunk_num * self.CHUNK_SIZE
            end_idx = min(start_idx + self.CHUNK_SIZE, len(firmware_data))
            chunk = firmware_data[start_idx:end_idx]
            
            # Try sending chunk with retries
            retry_count = 0
            success = False
            
            while retry_count < self.MAX_RETRIES and not success:
                self.status_updated.emit(
                    f"Sending chunk {chunk_num + 1}/{total_chunks} (Attempt {retry_count + 1})"
                )
                
                if not self.communicator.send_chunk(chunk):
                    retry_count += 1
                    time.sleep(0.1)
                    continue
                
                response = self.communicator.wait_for_response()
                
                if response == OTAResponse.ACK:
                    success = True
                    self.progress_updated.emit(chunk_num + 1, total_chunks)
                elif response in [OTAResponse.NACK, OTAResponse.ERROR, OTAResponse.TIMEOUT]:
                    retry_count += 1
                    self.status_updated.emit(
                        f"Received {response.value}, retrying... ({retry_count}/{self.MAX_RETRIES})"
                    )
                    time.sleep(0.2)
            
            if not success:
                self.status_updated.emit(
                    f"Failed to send chunk {chunk_num + 1} after {self.MAX_RETRIES} attempts"
                )
                return False
        
        self.status_updated.emit("Firmware update completed successfully!")
        return True


class OTAUpdaterGUI(QMainWindow):
    """Main GUI application"""
    
    def __init__(self):
        super().__init__()
        
        self.firmware_path = None
        self.update_worker = None
        
        self.init_ui()
        self.refresh_ports()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Leshuffler Firmware Update")
        self.setFixedSize(600, 550)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("Leshuffler Firmware Update")
        header.setAlignment(Qt.AlignCenter)
        header_font = QFont()
        header_font.setPointSize(20)
        header_font.setBold(True)
        header.setFont(header_font)
        main_layout.addWidget(header)
        
        # Serial Port Frame
        port_frame = self.create_frame()
        port_layout = QHBoxLayout(port_frame)
        
        port_label = QLabel("Serial Port:")
        port_layout.addWidget(port_label)
        
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(200)
        port_layout.addWidget(self.port_combo)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_ports)
        refresh_btn.setMaximumWidth(100)
        port_layout.addWidget(refresh_btn)
        
        port_layout.addStretch()
        main_layout.addWidget(port_frame)
        
        # File Selection Frame
        file_frame = self.create_frame()
        file_layout = QHBoxLayout(file_frame)
        
        self.file_label = QLabel("No file selected")
        file_layout.addWidget(self.file_label, 1)
        
        select_btn = QPushButton("Select Firmware (.sfb)")
        select_btn.clicked.connect(self.select_firmware)
        select_btn.setMinimumWidth(180)
        file_layout.addWidget(select_btn)
        
        main_layout.addWidget(file_frame)
        
        # Progress Frame
        progress_frame = self.create_frame()
        progress_layout = QVBoxLayout(progress_frame)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("0%")
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.progress_label)
        
        main_layout.addWidget(progress_frame)
        
        # Status Text
        status_label = QLabel("Status Log:")
        main_layout.addWidget(status_label)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(180)
        main_layout.addWidget(self.status_text)
        
        # Buttons Frame
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start OTA Update")
        self.start_btn.clicked.connect(self.start_update)
        self.start_btn.setMinimumHeight(45)
        start_font = QFont()
        start_font.setPointSize(11)
        start_font.setBold(True)
        self.start_btn.setFont(start_font)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #106EBE;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
            }
        """)
        btn_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop Update")
        self.stop_btn.clicked.connect(self.stop_update)
        self.stop_btn.setMinimumHeight(45)
        self.stop_btn.setFont(start_font)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #D13438;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #A52A2A;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
            }
        """)
        btn_layout.addWidget(self.stop_btn)
        
        main_layout.addLayout(btn_layout)
    
    def create_frame(self) -> QFrame:
        """Create a styled frame widget"""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                border: 1px solid #CCCCCC;
                border-radius: 5px;
                padding: 10px;
                background-color: #F9F9F9;
            }
        """)
        return frame
    
    def refresh_ports(self):
        """Refresh the list of serial ports"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        
        if ports:
            port_list = [port.device for port in ports]
            self.port_combo.addItems(port_list)
        else:
            self.port_combo.addItem("No ports found")
    
    def select_firmware(self):
        """Open file dialog to select firmware file"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Firmware File",
            "",
            "SFB Files (*.sfb);;All Files (*.*)"
        )
        
        if filepath:
            self.firmware_path = filepath
            filename = Path(filepath).name
            self.file_label.setText(filename)
            self.log_status(f"Selected: {filename}")
    
    def log_status(self, message: str):
        """Add message to status text box"""
        self.status_text.append(message)
    
    @Slot(int, int)
    def update_progress(self, current: int, total: int):
        """Update progress bar and label"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"{progress}% ({current}/{total} chunks)")
    
    def start_update(self):
        """Start the OTA update process"""
        # Validation
        if not self.firmware_path:
            QMessageBox.critical(self, "Error", "Please select a firmware file first")
            return
        
        if not Path(self.firmware_path).suffix == ".sfb":
            QMessageBox.critical(self, "Error", "Please select a valid .sfb file")
            return
        
        port = self.port_combo.currentText()
        if port == "No ports found" or not port:
            QMessageBox.critical(self, "Error", "Please select a valid serial port")
            return
        
        # Disable/enable controls
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("0%")
        
        # Create and start worker thread
        self.update_worker = FirmwareUpdateWorker(port, self.firmware_path)
        self.update_worker.progress_updated.connect(self.update_progress)
        self.update_worker.status_updated.connect(self.log_status)
        self.update_worker.update_completed.connect(self.on_update_completed)
        self.update_worker.start()
    
    def stop_update(self):
        """Stop the ongoing update"""
        if self.update_worker:
            self.update_worker.stop()
            self.log_status("Stopping update...")
    
    @Slot(bool)
    def on_update_completed(self, success: bool):
        """Handle update completion"""
        # Re-enable controls
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        # Show result message
        if success:
            QMessageBox.information(
                self,
                "Success",
                "Firmware update completed successfully!"
            )
        else:
            QMessageBox.critical(
                self,
                "Error",
                "Firmware update failed. Check status log for details."
            )


def main():
    """Entry point of the application"""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    window = OTAUpdaterGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()