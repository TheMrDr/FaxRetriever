import ctypes
import os
import time
import tempfile
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox
from SaveManager import SaveManager
from SystemLog import SystemLog


class CRxIntegration(QThread):
    finished = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.save_manager = SaveManager(self.main_window)
        self.log_system = SystemLog()
        self.dll_path = "C:\\Program Files (x86)\\Actian\\PSQL\\bin\\wbtrv32.dll"
        self.dll_path2 = "C:\\Program Files (x86)\\Pervasive Software\\PSQL\\bin\\wbtrv32.dll"
        self.failed_faxes = {}

        # Check if integration is enabled before proceeding
        integration_enabled = self.save_manager.get_config_value('Integrations', 'integration_enabled')
        crx_integration_enabled = self.save_manager.get_config_value('Integrations', 'integration_software')
        if integration_enabled.lower() != "yes" or crx_integration_enabled != "Computer-Rx":
            self.log_system.log_message('info', "Computer-Rx integration is disabled. Skipping initialization.")
            return

        winrx_path = self.save_manager.get_config_value('Integrations', 'winrx_path')
        if not winrx_path:
            self.log_system.log_message('error', "WinRx path not set. Integration cannot proceed.")
            QMessageBox.critical(self.main_window, "Integration Error",
                                 "WinRx integration is not configured properly. Please set the WinRx path in settings.")
            return

        # Perform case-insensitive search for FaxControl.btr
        try:
            faxcontrol_path = next(
                (os.path.join(winrx_path, f) for f in os.listdir(winrx_path) if f.lower() == "faxcontrol.btr"),
                None
            )
            if not faxcontrol_path:
                raise FileNotFoundError("FaxControl.btr not found in the specified directory.")
            faxcontrol_path = os.path.abspath(faxcontrol_path)  # Normalize path
            self.log_system.log_message('debug', f"Located FaxControl.btr at: {faxcontrol_path}")
        except Exception as e:
            self.log_system.log_message('error', f"Failed to locate FaxControl.btr: {e}")
            QMessageBox.critical(self.main_window, "Integration Error",
                                 "FaxControl.btr could not be found in the configured WinRx path.")
            return

        self.btrieve_file = faxcontrol_path.encode()
        self.fax_directory = winrx_path

        # Check if either DLL path exists
        if not os.path.exists(self.dll_path) and not os.path.exists(self.dll_path2):
            self.log_system.log_message('error', f"Btrieve DLL not found at {self.dll_path} or {self.dll_path2}")
            QMessageBox.critical(self.main_window, "Critical Error",
                                 "Btrieve DLL not found. Ensure Actian PSQL is installed correctly.")
            return

        # Use whichever DLL path is found
        dll_to_load = self.dll_path if os.path.exists(self.dll_path) else self.dll_path2

        try:
            self.btrieve = ctypes.WinDLL(dll_to_load)
            self.log_system.log_message('info', f"Successfully loaded Btrieve DLL from {dll_to_load}.")
        except OSError as e:
            self.log_system.log_message('error', f"Failed to load Btrieve DLL: {e}")
            QMessageBox.critical(self.main_window, "Critical Error", f"Failed to load Btrieve DLL: {e}")
            return

        self.B_OPEN = 0
        self.B_GET_FIRST = 12
        self.B_GET_NEXT = 6
        self.B_DELETE = 4
        self.B_CLOSE = 1
        self.B_EOF = 9

        self.BUFFER_LENGTH = 215
        self.DATA_BUFFER = ctypes.create_string_buffer(self.BUFFER_LENGTH)
        self.POSITION_BLOCK = ctypes.create_string_buffer(128)
        self.KEY_BUFFER = ctypes.create_string_buffer(4)
        self.KEY_LENGTH = ctypes.c_ushort(4)
        self.KEY_NUMBER = ctypes.c_ushort(0)

    def run(self):
        self.process_faxes_demo()
        self.finished.emit()

    def process_faxes_demo(self):
        """Reads records from FaxControl.btr and logs what would have been sent in demo mode."""
        data_length = ctypes.c_ushort(self.BUFFER_LENGTH)
        self.log_system.log_message('debug', f"Attempting to open Btrieve file: {self.btrieve_file.decode()}")

        status = self.btrieve.BTRCALL(self.B_OPEN, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length),
                                      self.btrieve_file, 0, None)

        if status != 0:
            self.log_system.log_message('error',
                                        f"Failed to open Btrieve file: {self.btrieve_file.decode()} | Status Code: {status}")
            return

        self.log_system.log_message('info', "Processing faxes from FaxControl.btr (DEMO MODE - No actual sending)")
        status = self.btrieve.BTRCALL(self.B_GET_FIRST, self.POSITION_BLOCK, self.DATA_BUFFER,
                                      ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_LENGTH, None)

        while status == 0:
            raw_data = self.DATA_BUFFER.raw[:data_length.value]
            record_id = int.from_bytes(raw_data[0:4], 'little')
            phone_number = raw_data[4:18].decode('ascii', errors='ignore').strip()
            file_name = raw_data[27:80].decode('ascii', errors='ignore').strip()
            full_file_path = os.path.join(self.fax_directory, file_name)

            if not phone_number or not file_name:
                self.log_system.log_message('error', f"Invalid record detected (ID: {record_id}). Skipping.")
            else:
                self.log_system.log_message('info',
                                            f"DEMO: Would send fax - Record {record_id}: {phone_number} - {full_file_path}")

            data_length.value = self.BUFFER_LENGTH
            status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
                                          ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)

            if status == self.B_EOF:
                self.log_system.log_message('info', "Reached End of File. Stopping retrieval.")
                break
            elif status != 0:
                self.log_system.log_message('error', f"Failed to retrieve next record. Status Code: {status}")
                break

        self.btrieve.BTRCALL(self.B_CLOSE, self.POSITION_BLOCK, None, None, None, 0, None)
        self.log_system.log_message('info', "Fax processing complete (DEMO MODE)")