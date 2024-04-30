import logging
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
        self.setup_logger()

    def setup_logger(self):
        self.logger = logging.getLogger('ClinicFax')
        self.logger.setLevel(logging.INFO)  # Initial conservative default
        if not self.logger.handlers:
            fh = RotatingFileHandler('.\\log\\ClinicFax.log', maxBytes=512 * 512, backupCount=3)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(fh)
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
