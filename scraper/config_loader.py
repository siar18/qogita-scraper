import json
import os

REQUIRED_FIELDS = ["qogita_email", "qogita_password", "google_sheet_url", "margin_divisor", "headless"]


class ConfigError(Exception):
    pass


def load_config(path: str = "config.json") -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        config = json.load(f)
    for field in REQUIRED_FIELDS:
        if field not in config:
            raise ConfigError(f"Missing required config field: {field}")
    return config
