# config_loader.py
# Strict separation of Global and Device config loaders

import json
import os
from typing import Any, Optional
from utils.logging_utils import get_logger

GLOBAL_CONFIG_PATH = os.path.join("shared", "config", "config.json")
LOCAL_CONFIG_PATH = os.path.join(
    os.getenv("LOCALAPPDATA"),
    "Clinic Networking, LLC",
    "FaxRetriever",
    "2.0",
    "config.json"
)


class BaseConfigLoader:
    def __init__(self, path: str, label: str):
        self.path = path
        self.label = label
        self.config = {}
        self.log = get_logger(label)
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                    self.log.info(f"{self.label} config loaded.")
            else:
                self.log.warning(f"{self.label} config file not found; using defaults.")
                self.config = {}
        except Exception as e:
            self.log.exception(f"Failed to load {self.label} config: {e}")
            self.config = {}

    def get(self, section: str, key: str, fallback: Optional[Any] = None) -> Any:
        return self.config.get(section, {}).get(key, fallback)

    def set(self, section: str, key: str, value: Any):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            self.log.info(f"{self.label} config saved.")
        except Exception as e:
            self.log.exception(f"Failed to save {self.label} config: {e}")


class GlobalConfigLoader(BaseConfigLoader):
    def __init__(self):
        super().__init__(GLOBAL_CONFIG_PATH, "Global")


class DeviceConfigLoader(BaseConfigLoader):
    def __init__(self):
        super().__init__(LOCAL_CONFIG_PATH, "Device")


# Exported instances
global_config = GlobalConfigLoader()
device_config = DeviceConfigLoader()
