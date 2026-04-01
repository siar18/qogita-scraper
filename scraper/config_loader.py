import json
import os
from typing import Any

REQUIRED_FIELDS = ["qogita_email", "qogita_password", "google_sheet_url", "margin_divisor", "headless", "anthropic_api_key"]


class ConfigError(Exception):
    pass


def load_config(path: str = "config.json") -> dict[str, Any]:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        config = json.load(f)
    for field in REQUIRED_FIELDS:
        if field not in config:
            raise ConfigError(f"Missing required config field: {field}")
    return config
