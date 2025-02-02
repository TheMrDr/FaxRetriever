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

        # Load archival settings
        self.archive_enabled = self.save_manager.get_config_value('Fax Options', 'archive_enabled') == "Yes"
        self.archive_duration = int(
            self.save_manager.get_config_value('Fax Options', 'archive_duration') or 30)  # Default to 30 days
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
