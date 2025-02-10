import os
import datetime
import shutil
from SaveManager import SaveManager
from SystemLog import SystemLog


class ArchiveManager:
    def __init__(self, main_window=None):
        self.main_window = main_window
        self.log_system = SystemLog()
        self.save_manager = SaveManager(self.main_window)

        # Load archival settings safely
        archive_enabled_raw = self.save_manager.get_config_value('Fax Options', 'archive_enabled')

        # If the key is missing or invalid, default to "No"
        self.archive_enabled = archive_enabled_raw == "Yes" if archive_enabled_raw else False

        # Load and validate archive duration
        raw_duration = self.save_manager.get_config_value('Fax Options', 'archive_duration')

        # Ensure the retrieved value is a valid integer
        try:
            if raw_duration and raw_duration.isdigit():  # Ensure it contains only digits
                self.archive_duration = int(raw_duration)
            else:
                raise ValueError  # Trigger the exception if it's not a valid number
        except (ValueError, TypeError):
            self.log_system.log_message('warning',
                                        f"Invalid archive duration value: {raw_duration}. Defaulting to 30 days.")
            self.archive_duration = 30  # Default to 30 days if invalid

        self.archive_path = os.path.join(os.getcwd(), "Archive")

    def cleanup_old_archives(self):
        """Delete archived faxes that exceed the retention period."""
        if not self.archive_enabled:
            self.log_system.log_message('info', "Archiving is disabled, skipping cleanup.")
            return

        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.archive_duration)
            for date_folder in os.listdir(self.archive_path):
                folder_path = os.path.join(self.archive_path, date_folder)

                if os.path.isdir(folder_path):
                    folder_date = datetime.datetime.strptime(date_folder, "%Y-%m-%d")

                    # Remove folders older than the archival period
                    if folder_date < cutoff_date:
                        shutil.rmtree(folder_path)
                        self.log_system.log_message('info', f"Deleted old archive folder: {folder_path}")

        except Exception as e:
            self.log_system.log_message('error', f"Error cleaning up archive: {e}")


if __name__ == "__main__":
    archive_manager = ArchiveManager()
    archive_manager.cleanup_old_archives()
