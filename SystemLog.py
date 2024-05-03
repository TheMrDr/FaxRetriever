import logging
import os
from logging.handlers import RotatingFileHandler

from PyQt5.QtWidgets import QAction
import os


class SystemLog(QAction):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SystemLog, cls).__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = None
        self.setup_logger()

    def setup_logger(self):
        log_directory = './log'
        log_file_path = os.path.join(log_directory, 'ClinicFax.log')

        # Ensure the log directory exists
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)  # Create the directory if it does not exist

        self.logger = logging.getLogger('ClinicFax')
        self.logger.setLevel(logging.INFO)  # Set initial logging level

        # Check if handlers already exist to avoid duplicate logging
        if not self.logger.handlers:
            # Set up rotating file handler
            fh = RotatingFileHandler(log_file_path, maxBytes=512 * 512, backupCount=3)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(fh)

            # Optional: Set up stream handler to also echo logs to console
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(ch)

    def refresh_logging_level(self, level):
        level_mapping = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        new_level = level_mapping.get(level, logging.INFO)
        self.logger.setLevel(new_level)
        for handler in self.logger.handlers:
            handler.setLevel(new_level)

    def log_message(self, level, message):
        getattr(self.logger, level.lower(), self.logger.info)(message)
