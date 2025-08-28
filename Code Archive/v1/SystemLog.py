import logging
import os
from logging.handlers import RotatingFileHandler

from PyQt5.QtWidgets import QAction


class SystemLog(QAction):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SystemLog, cls).__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = None
        self.current_logging_level = logging.INFO  # Default logging level
        self.setup_logger()

    def setup_logger(self):
        try:
            log_directory = './log'
            log_file_path = os.path.join(log_directory, 'ClinicFax.log')

            # Ensure the log directory exists
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)  # Create the directory if it does not exist

            self.logger = logging.getLogger('ClinicFax')
            self.logger.setLevel(self.current_logging_level)

            # Check if handlers already exist to avoid duplicate logging
            if not self.logger.handlers:
                # Set up rotating file handler (500KB max per file, 3 backups)
                fh = RotatingFileHandler(log_file_path, maxBytes=500 * 1024, backupCount=3)
                fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                self.logger.addHandler(fh)
        except Exception as e:
            print(f"Failed to set up logger: {e}")

    def refresh_logging_level(self, level):
        try:
            level_mapping = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            new_level = level_mapping.get(level.upper(), logging.INFO)
            self.current_logging_level = new_level
            self.logger.setLevel(new_level)
            for handler in self.logger.handlers:
                handler.setLevel(new_level)
        except Exception as e:
            self.log_message('error', f"Failed to refresh logging level: {e}")

    def log_message(self, level, message):
        try:
            level_mapping = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            log_level = level_mapping.get(level.upper(), logging.INFO)

            # Only log messages that meet or exceed the configured logging level
            if log_level >= self.current_logging_level:
                getattr(self.logger, level.lower(), self.logger.info)(message)
        except Exception as e:
            print(f"Failed to log message: {e}")
