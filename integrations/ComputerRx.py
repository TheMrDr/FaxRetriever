import ctypes
import os
import re
import time
import tempfile
import requests
from PyQt5.QtCore import QThread, pyqtSignal, QMetaObject, Qt
from PyQt5.QtWidgets import QMessageBox
from SaveManager import SaveManager
from SystemLog import SystemLog


class CRxIntegration(QThread):
    finished = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        print("DEBUG: Entering CRxIntegration.__init__()")  # Print to console
        if self.main_window:
            self.main_window.log_system.log_message('debug', "DEBUG: Entering CRxIntegration.__init__()")

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
        self.process_faxes()
        self.finished.emit()

    @staticmethod
    def format_phone_number(phone_number, caller_id):
        """Ensure phone number is always formatted as an 11-digit number."""

        # Strip all non-numeric characters from both phone_number and caller_id
        phone_number = re.sub(r'\D', '', phone_number)
        caller_id = re.sub(r'\D', '', caller_id)

        # Ensure caller_id is at least 11 digits before extracting area code
        if len(caller_id) == 11:
            area_code = caller_id[1:4]  # Extract the area code from caller_id
        else:
            area_code = "000"  # Fallback in case of unexpected caller_id format

        # Apply standard formatting rules
        if len(phone_number) == 7:
            phone_number = "1" + area_code + phone_number
        elif len(phone_number) == 10:
            phone_number = "1" + phone_number
        elif len(phone_number) != 11:
            return ""  # Invalid number, return empty string

        return phone_number

    # def process_faxes_demo(self):
    #     """Reads records from FaxControl.btr and logs faxes that would be sent in demo mode."""
    #     self.log_system.log_message('debug', "Starting process_faxes_demo")
    #
    #     data_length = ctypes.c_ushort(215)
    #     status = self.btrieve.BTRCALL(self.B_OPEN, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length),
    #                                   self.btrieve_file, 0, None)
    #
    #     if status != 0:
    #         self.log_system.log_message('error',
    #                                     f"Failed to open Btrieve file: {self.btrieve_file.decode()} | Status Code: {status}")
    #         return
    #
    #     self.log_system.log_message('info', "Processing faxes from FaxControl.btr (DEMO MODE - No actual sending)")
    #     status = self.btrieve.BTRCALL(self.B_GET_FIRST, self.POSITION_BLOCK, self.DATA_BUFFER,
    #                                   ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_LENGTH, None)
    #
    #     fax_user = self.save_manager.get_config_value('Account', 'fax_user')
    #     token = self.save_manager.get_config_value('Token', 'access_token')
    #     caller_id = self.save_manager.get_config_value('Retrieval', 'fax_caller_id').strip()
    #
    #     self.log_system.log_message('debug', "Beginning record processing loop")
    #     while status == 0:
    #         self.log_system.log_message('debug', f"Processing record with status: {status}")
    #         raw_data = self.DATA_BUFFER.raw[:data_length.value]
    #
    #         record_id = int.from_bytes(raw_data[0:4], 'little')
    #         phone_number = raw_data[4:18].decode('ascii', errors='ignore').replace('\x00', '').strip()
    #         phone_number = re.sub(r'\D', '', phone_number)  # Strip all non-numeric characters
    #
    #         file_name = raw_data[27:80].decode('ascii', errors='ignore').replace('\x00', '').strip()
    #         full_file_path = os.path.join(self.fax_directory, file_name)
    #
    #         formatted_destination_number = self.format_phone_number(phone_number, caller_id)
    #
    #         self.log_system.log_message('debug',
    #                                     f"Record {record_id}: Parsed Phone - {formatted_destination_number}, File - {full_file_path}")
    #
    #         # Validate phone number length (must be 11 digits)
    #         if len(formatted_destination_number) != 11:
    #             self.log_system.log_message('error',
    #                                         f"Invalid phone number detected (ID: {record_id}, Number: {formatted_destination_number}). Skipping.")
    #             status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
    #                                           ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
    #             continue  # Skip to next record
    #
    #         # Validate if the file exists before proceeding
    #         if not os.path.exists(full_file_path):
    #             self.log_system.log_message('error',
    #                                         f"Missing fax file detected (ID: {record_id}, File: {full_file_path}). Skipping.")
    #             status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
    #                                           ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
    #             continue  # Skip to next record
    #
    #         # Log what we would have sent (in demo mode)
    #         self.log_system.log_message('info',
    #                                     f"DEMO: Would send fax - Record {record_id}: User: {fax_user}, Caller ID: {caller_id}, Destination: {formatted_destination_number}, File: {full_file_path}")
    #
    #         status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
    #                                       ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
    #
    #         self.log_system.log_message('debug', f"Next record status: {status}")
    #
    #         if status == self.B_EOF:
    #             self.log_system.log_message('info', "Reached End of File. Stopping retrieval.")
    #             break
    #         elif status != 0:
    #             self.log_system.log_message('error', f"Failed to retrieve next record. Status Code: {status}")
    #             break
    #
    #     self.btrieve.BTRCALL(self.B_CLOSE, self.POSITION_BLOCK, None, None, None, 0, None)
    #     self.log_system.log_message('info', "Fax processing complete (DEMO MODE)")


    def process_faxes(self):
        """Reads records from FaxControl.btr and sends real faxes via API."""
        self.log_system.log_message('debug', "Starting process_faxes")

        data_length = ctypes.c_ushort(215)
        status = self.btrieve.BTRCALL(self.B_OPEN, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length),
                                      self.btrieve_file, 0, None)

        if status != 0:
            self.log_system.log_message('error',
                                        f"Failed to open Btrieve file: {self.btrieve_file.decode()} | Status Code: {status}")
            return

        self.log_system.log_message('info', "Processing faxes from FaxControl.btr (LIVE MODE - Sending faxes)")
        status = self.btrieve.BTRCALL(self.B_GET_FIRST, self.POSITION_BLOCK, self.DATA_BUFFER,
                                      ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_LENGTH, None)

        fax_user = self.save_manager.get_config_value('Account', 'fax_user')
        token = self.save_manager.get_config_value('Token', 'access_token')
        caller_id = self.save_manager.get_config_value('Retrieval', 'fax_caller_id').strip()

        self.log_system.log_message('debug', "Beginning record processing loop")
        while status == 0:
            self.log_system.log_message('debug', f"Processing record with status: {status}")
            raw_data = self.DATA_BUFFER.raw[:data_length.value]

            record_id = int.from_bytes(raw_data[0:4], 'little')
            phone_number = raw_data[4:18].decode('ascii', errors='ignore').replace('\x00', '').strip()
            phone_number = re.sub(r'\D', '', phone_number)  # Strip all non-numeric characters

            file_name = raw_data[27:80].decode('ascii', errors='ignore').replace('\x00', '').strip()
            full_file_path = os.path.join(self.fax_directory, file_name)

            formatted_destination_number = self.format_phone_number(phone_number, caller_id)

            self.log_system.log_message('debug',
                                        f"Record {record_id}: Parsed Phone - {formatted_destination_number}, File - {full_file_path}")

            # Validate phone number length (must be 11 digits)
            if len(formatted_destination_number) != 11:
                self.log_system.log_message('error',
                                            f"Invalid phone number detected (ID: {record_id}, Number: {formatted_destination_number}). Skipping.")
                status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
                                              ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                continue  # Skip to next record

            # Validate if the file exists before proceeding
            if not os.path.exists(full_file_path):
                self.log_system.log_message('error',
                                            f"Missing fax file detected (ID: {record_id}, File: {full_file_path}). Skipping.")
                status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
                                              ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                continue  # Skip to next record

            # SEND FAX
            url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
            headers = {"Authorization": f"Bearer {token}"}
            files = {"filename": (os.path.basename(full_file_path), open(full_file_path, 'rb'), 'application/pdf')}
            data = {"caller_id": caller_id, "destination": formatted_destination_number}

            try:
                response = requests.post(url, files=files, data=data, headers=headers)
                if response.status_code == 200:
                    self.log_system.log_message('info', f"Fax successfully sent (ID: {record_id}) to {formatted_destination_number}. Removing record.")

                    # REMOVE RECORD FROM BTRIEVE
                    delete_status = self.btrieve.BTRCALL(self.B_DELETE, self.POSITION_BLOCK, self.DATA_BUFFER,
                                                         ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    if delete_status != 0:
                        self.log_system.log_message('error', f"Failed to remove record (ID: {record_id}) from Btrieve. Status Code: {delete_status}")

                    # DELETE PDF FILE
                    try:
                        os.remove(full_file_path)
                        self.log_system.log_message('info', f"Deleted fax file: {full_file_path}")
                    except Exception as e:
                        self.log_system.log_message('error', f"Failed to delete fax file: {full_file_path} | Error: {str(e)}")

                else:
                    self.log_system.log_message('error', f"Failed to send fax (ID: {record_id}) to {formatted_destination_number}. Response: {response.text}")

            except Exception as e:
                self.log_system.log_message('error', f"Error sending fax (ID: {record_id}): {str(e)}")

            finally:
                files["filename"][1].close()  # Close the file handle

            # Move to next record
            status = self.btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER,
                                          ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)

            self.log_system.log_message('debug', f"Next record status: {status}")

            if status == self.B_EOF:
                self.log_system.log_message('info', "Reached End of File. Stopping retrieval.")
                break
            elif status != 0:
                self.log_system.log_message('error', f"Failed to retrieve next record. Status Code: {status}")
                break

        self.btrieve.BTRCALL(self.B_CLOSE, self.POSITION_BLOCK, None, None, None, 0, None)
        self.log_system.log_message('info', "Fax processing complete (LIVE MODE)")
