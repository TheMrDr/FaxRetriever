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

        # Determine logging level
        self.logging_level = self.save_manager.get_config_value('UserSettings', 'logging_level').upper()
        self.log_system.refresh_logging_level(self.logging_level)  # Apply logging level dynamically

        # Load archival settings safely
        archive_enabled_raw = self.save_manager.get_config_value('Fax Options', 'archive_enabled') or "No"
        archive_enabled_raw = archive_enabled_raw.strip().lower()

        if archive_enabled_raw not in ["yes", "no"]:
            self.log_system.log_message('error', f"Invalid archive_enabled value: {archive_enabled_raw}. Defaulting to No.")
            self.archive_enabled = False
        else:
            self.archive_enabled = archive_enabled_raw == "yes"

        raw_duration = self.save_manager.get_config_value('Fax Options', 'archive_duration')
        try:
            self.archive_duration = int(raw_duration) if raw_duration and raw_duration.isdigit() else 30
        except (ValueError, TypeError):
            self.log_system.log_message('warning', f"Invalid archive duration value: {raw_duration}. Defaulting to 30 days.")
            self.archive_duration = 30

        self.archive_path = os.path.join(os.getcwd(), "Archive")

    def cleanup_old_archives(self):
        """Delete archived faxes that exceed the retention period."""
        if not self.archive_enabled:
            self.log_system.log_message('info', "Archiving is disabled, skipping cleanup.")
            return

        if not os.path.exists(self.archive_path):
            self.log_system.log_message('warning', "Archive directory does not exist, skipping cleanup.")
            return

        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.archive_duration)

            for date_folder in os.listdir(self.archive_path):
                folder_path = os.path.join(self.archive_path, date_folder)

                if not os.path.isdir(folder_path):
                    continue  # Skip files, only process directories

                try:
                    folder_date = datetime.datetime.strptime(date_folder, "%Y-%m-%d")

                    if folder_date < cutoff_date:
                        shutil.rmtree(folder_path)
                        self.log_system.log_message('info', f"Deleted old archive folder: {folder_path}")

                except ValueError:
                    self.log_system.log_message('warning', f"Skipping non-date folder in archive: {date_folder}")

        except Exception as e:
            self.log_system.log_message('error', f"Error cleaning up archive: {e}")


if __name__ == "__main__":
    archive_manager = ArchiveManager()
    archive_manager.cleanup_old_archives()
