import json

from lib import config
from lib.storage import read_sensitive_json, write_sensitive_json


def test_config_clamps_date_range(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"date_range_days": 999}), encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", str(path))
    monkeypatch.setattr(config, "LEGACY_CONFIG_FILE", str(tmp_path / "missing.json"))

    assert config.Config().date_range_days == 30


def test_config_recovers_from_invalid_json(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", str(path))
    monkeypatch.setattr(config, "LEGACY_CONFIG_FILE", str(tmp_path / "missing.json"))

    assert config.Config().date_range_days == config.DEFAULT_CONFIG["date_range_days"]


def test_sensitive_json_round_trip(tmp_path):
    path = tmp_path / "secret.json"
    value = {"cookie": "sensitive-value", "name": "测试用户"}

    write_sensitive_json(path, value)

    assert read_sensitive_json(path) == value
