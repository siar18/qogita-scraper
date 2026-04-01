import json
import os
import pytest
from scraper.config_loader import load_config, ConfigError


def test_load_config_returns_all_fields(tmp_path):
    cfg = {
        "qogita_email": "test@test.com",
        "qogita_password": "secret",
        "google_sheet_url": "https://example.com/sheet",
        "margin_divisor": 1.12,
        "headless": True,
        "anthropic_api_key": "sk-test-key"
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg))
    result = load_config(str(config_file))
    assert result["qogita_email"] == "test@test.com"
    assert result["margin_divisor"] == 1.12
    assert result["headless"] is True


def test_load_config_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.json")


def test_load_config_missing_required_field_raises(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"qogita_email": "x@x.com"}))
    with pytest.raises(ConfigError, match="qogita_password"):
        load_config(str(config_file))
