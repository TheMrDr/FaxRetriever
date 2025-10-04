# config_loader.py
# Strict separation of Global and Device config loaders

import json
import os
import sys
from typing import Any, Optional
from utils.logging_utils import get_logger


def _resolve_global_config_path() -> str:
    cands: list[str] = []

    # 1) Explicit override by file or dir
    env_file = os.environ.get('FR_GLOBAL_CONFIG_FILE')
    if env_file:
        if os.path.isdir(env_file):
            cands.append(os.path.join(env_file, 'config.json'))
        else:
            cands.append(env_file)

    env_dir = os.environ.get('FR_GLOBAL_CONFIG_DIR')
    if env_dir:
        cands.append(os.path.join(env_dir, 'config.json'))

    # 2) Original network launch root provided by bootstrap
    orig_root = os.environ.get('FR_ORIGINAL_ROOT')
    if orig_root:
        cands.append(os.path.join(orig_root, 'shared', 'config', 'config.json'))

    # 3) Origin path file written by bootstrap in local cache bin
    try:
        local_appdata = os.environ.get('LOCALAPPDATA') or ''
        origin_file = os.path.join(local_appdata, 'Clinic Networking, LLC', 'FaxRetriever', '2.0', 'bin', 'origin.path')
        if os.path.exists(origin_file):
            with open(origin_file, 'r', encoding='utf-8') as f:
                origin_root = f.read().strip()
                if origin_root:
                    cands.append(os.path.join(origin_root, 'shared', 'config', 'config.json'))
    except Exception:
        pass

    # 4) Path relative to the running process directory (exe or script)
    try:
        proc_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        cands.append(os.path.join(proc_dir, 'shared', 'config', 'config.json'))
    except Exception:
        pass

    # 5) Path relative to project root when running from source (..\.. from src\core)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        proj_root = os.path.abspath(os.path.join(here, '..', '..'))
        cands.append(os.path.join(proj_root, 'shared', 'config', 'config.json'))
    except Exception:
        pass

    # 6) Original default relative path (CWD)
    cands.append(os.path.join('shared', 'config', 'config.json'))

    # Select the first existing path
    for p in cands:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            continue

    # If none exist, prefer using the original root (so a new shared config is created there)
    if orig_root:
        return os.path.join(orig_root, 'shared', 'config', 'config.json')

    # Fallback to process-relative path
    try:
        return os.path.join(proc_dir, 'shared', 'config', 'config.json')  # type: ignore[name-defined]
    except Exception:
        # Last resort: current working directory
        return os.path.join('shared', 'config', 'config.json')


GLOBAL_CONFIG_PATH = _resolve_global_config_path()

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
