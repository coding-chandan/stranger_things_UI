"""
Leshuffler Firmware OTA Updater
A modular GUI application for performing Over-The-Air firmware updates via serial interface
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import serial
import serial.tools.list_ports
import threading
import time
from pathlib import Path
from typing import Optional, Callable
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


class FirmwareUpdater:
    """Handles the firmware update logic"""
    
    CHUNK_SIZE = 1024  # 1 KB
    MAX_RETRIES = 3
    
    def __init__(self, communicator: SerialCommunicator):
        self.communicator = communicator
        self.is_updating = False
        self.should_stop = False
    
    def load_firmware(self, filepath: str) -> Optional[bytes]:
        """Load firmware file into memory"""
        try:
            with open(filepath, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"File load error: {e}")
            return None
    
    def update_firmware(
        self,
        firmware_data: bytes,
        progress_callback: Callable[[int, int], None],
        status_callback: Callable[[str], None]
    ) -> bool:
        """
        Perform the OTA update process
        
        Args:
            firmware_data: Binary firmware data
            progress_callback: Function to update progress (current, total)
            status_callback: Function to update status message
        
        Returns:
            True if successful, False otherwise
        """
        self.is_updating = True
        self.should_stop = False
        
        total_chunks = (len(firmware_data) + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
        
        status_callback(f"Starting OTA update... ({total_chunks} chunks)")
        
        for chunk_num in range(total_chunks):
            if self.should_stop:
                status_callback("Update cancelled by user")
                self.is_updating = False
                return False
            
            start_idx = chunk_num * self.CHUNK_SIZE
            end_idx = min(start_idx + self.CHUNK_SIZE, len(firmware_data))
            chunk = firmware_data[start_idx:end_idx]
            
            # Try sending chunk with retries
            retry_count = 0
            success = False
            
            while retry_count < self.MAX_RETRIES and not success:
                status_callback(f"Sending chunk {chunk_num + 1}/{total_chunks} (Attempt {retry_count + 1})")
                
                if not self.communicator.send_chunk(chunk):
                    retry_count += 1
                    time.sleep(0.1)
                    continue
                
                response = self.communicator.wait_for_response()
                
                if response == OTAResponse.ACK:
                    success = True
                    progress_callback(chunk_num + 1, total_chunks)
                elif response in [OTAResponse.NACK, OTAResponse.ERROR, OTAResponse.TIMEOUT]:
                    retry_count += 1
                    status_callback(f"Received {response.value}, retrying... ({retry_count}/{self.MAX_RETRIES})")
                    time.sleep(0.2)
            
            if not success:
                status_callback(f"Failed to send chunk {chunk_num + 1} after {self.MAX_RETRIES} attempts")
                self.is_updating = False
                return False
        
        status_callback("Firmware update completed successfully!")
        self.is_updating = False
        return True
    
    def stop_update(self):
        """Stop the ongoing update"""
        self.should_stop = True


class OTAUpdaterGUI:
    """Main GUI application"""
    
    def __init__(self):
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Initialize window
        self.window = ctk.CTk()
        self.window.title("Leshuffler Firmware Update")
        self.window.geometry("600x500")
        self.window.resizable(False, False)
        
        # Variables
        self.firmware_path = None
        self.communicator = None
        self.updater = None
        self.update_thread = None
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create and layout all GUI widgets"""
        
        # Header
        header = ctk.CTkLabel(
            self.window,
            text="Leshuffler Firmware Update",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        header.pack(pady=20)
        
        # Serial Port Frame
        port_frame = ctk.CTkFrame(self.window)
        port_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(port_frame, text="Serial Port:").pack(side="left", padx=10)
        
        self.port_dropdown = ctk.CTkComboBox(
            port_frame,
            values=self._get_serial_ports(),
            width=200
        )
        self.port_dropdown.pack(side="left", padx=10)
        
        refresh_btn = ctk.CTkButton(
            port_frame,
            text="Refresh",
            command=self._refresh_ports,
            width=100
        )
        refresh_btn.pack(side="left", padx=10)
        
        # File Selection Frame
        file_frame = ctk.CTkFrame(self.window)
        file_frame.pack(pady=10, padx=20, fill="x")
        
        self.file_label = ctk.CTkLabel(
            file_frame,
            text="No file selected",
            anchor="w"
        )
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)
        
        select_btn = ctk.CTkButton(
            file_frame,
            text="Select Firmware (.sfb)",
            command=self._select_firmware,
            width=180
        )
        select_btn.pack(side="right", padx=10)
        
        # Progress Frame
        progress_frame = ctk.CTkFrame(self.window)
        progress_frame.pack(pady=20, padx=20, fill="x")
        
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(pady=10, padx=10, fill="x")
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(progress_frame, text="0%")
        self.progress_label.pack()
        
        # Status Text
        self.status_text = ctk.CTkTextbox(self.window, height=150, state="disabled")
        self.status_text.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Buttons Frame
        btn_frame = ctk.CTkFrame(self.window)
        btn_frame.pack(pady=10, padx=20, fill="x")
        
        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="Start OTA Update",
            command=self._start_update,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.start_btn.pack(side="left", padx=10, expand=True)
        
        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="Stop Update",
            command=self._stop_update,
            width=200,
            height=40,
            state="disabled",
            fg_color="red",
            hover_color="darkred"
        )
        self.stop_btn.pack(side="right", padx=10, expand=True)
    
    def _get_serial_ports(self) -> list:
        """Get list of available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports] if ports else ["No ports found"]
    
    def _refresh_ports(self):
        """Refresh the list of serial ports"""
        ports = self._get_serial_ports()
        self.port_dropdown.configure(values=ports)
        if ports:
            self.port_dropdown.set(ports[0])
    
    def _select_firmware(self):
        """Open file dialog to select firmware file"""
        filepath = filedialog.askopenfilename(
            title="Select Firmware File",
            filetypes=[("SFB Files", "*.sfb"), ("All Files", "*.*")]
        )
        
        if filepath:
            self.firmware_path = filepath
            filename = Path(filepath).name
            self.file_label.configure(text=filename)
            self._log_status(f"Selected: {filename}")
    
    def _log_status(self, message: str):
        """Add message to status text box"""
        self.status_text.configure(state="normal")
        self.status_text.insert("end", f"{message}\n")
        self.status_text.see("end")
        self.status_text.configure(state="disabled")
    
    def _update_progress(self, current: int, total: int):
        """Update progress bar and label"""
        progress = current / total
        percentage = int(progress * 100)
        
        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{percentage}% ({current}/{total} chunks)")
    
    def _start_update(self):
        """Start the OTA update process"""
        # Validation
        if not self.firmware_path:
            messagebox.showerror("Error", "Please select a firmware file first")
            return
        
        if not Path(self.firmware_path).suffix == ".sfb":
            messagebox.showerror("Error", "Please select a valid .sfb file")
            return
        
        port = self.port_dropdown.get()
        if port == "No ports found" or not port:
            messagebox.showerror("Error", "Please select a valid serial port")
            return
        
        # Disable controls
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress_bar.set(0)
        
        # Start update in separate thread
        self.update_thread = threading.Thread(
            target=self._perform_update,
            args=(port,),
            daemon=True
        )
        self.update_thread.start()
    
    def _perform_update(self, port: str):
        """Perform the actual update process (runs in separate thread)"""
        try:
            # Initialize communicator
            self._log_status(f"Connecting to {port}...")
            self.communicator = SerialCommunicator(port)
            
            if not self.communicator.connect():
                self._log_status("Failed to connect to device")
                messagebox.showerror("Error", "Failed to connect to serial port")
                self._reset_ui()
                return
            
            self._log_status("Connected successfully")
            
            # Initialize updater
            self.updater = FirmwareUpdater(self.communicator)
            
            # Load firmware
            self._log_status("Loading firmware file...")
            firmware_data = self.updater.load_firmware(self.firmware_path)
            
            if not firmware_data:
                self._log_status("Failed to load firmware file")
                messagebox.showerror("Error", "Failed to load firmware file")
                self._reset_ui()
                return
            
            self._log_status(f"Firmware loaded: {len(firmware_data)} bytes")
            
            # Perform update
            success = self.updater.update_firmware(
                firmware_data,
                self._update_progress,
                self._log_status
            )
            
            # Show result
            if success:
                messagebox.showinfo("Success", "Firmware update completed successfully!")
            else:
                messagebox.showerror("Error", "Firmware update failed. Check status log.")
            
        except Exception as e:
            self._log_status(f"Unexpected error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        
        finally:
            if self.communicator:
                self.communicator.disconnect()
            self._reset_ui()
    
    def _stop_update(self):
        """Stop the ongoing update"""
        if self.updater:
            self.updater.stop_update()
            self._log_status("Stopping update...")
    
    def _reset_ui(self):
        """Reset UI controls after update completion"""
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
    
    def run(self):
        """Start the GUI application"""
        self.window.mainloop()


def main():
    """Entry point of the application"""
    app = OTAUpdaterGUI()
    app.run()


if __name__ == "__main__":
    main()