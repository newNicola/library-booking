import datetime

import pytest

from server import app as app_module
from server import db


@pytest.fixture
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_health_reflects_database_state(client, monkeypatch):
    monkeypatch.setattr(app_module.db, "check_health", lambda: False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["status"] == "error"


def test_booking_log_rejects_invalid_date(client):
    response = client.post("/log_booking", json={
        "seat": "2001",
        "date": "not-a-date",
        "begin": "08:00",
        "end": "09:59",
    })

    assert response.status_code == 400


def test_booking_log_normalizes_allowed_fields(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(app_module.db, "insert_booking", lambda payload: captured.update(payload))

    response = client.post("/log_booking", json={
        "user_id": " 20260001 ",
        "seat": " 2001 ",
        "date": "2026-09-13",
        "begin": "08:00",
        "end": "09:59",
        "ignored": "not persisted",
    })

    assert response.status_code == 200
    assert captured["user_id"] == "20260001"
    assert captured["seat"] == "2001"
    assert "ignored" not in captured


def test_check_key_ignores_invisible_copy_paste_characters(client, monkeypatch):
    monkeypatch.setattr(app_module.config, "JWT_SECRET", "j" * 32)
    monkeypatch.setattr(app_module.db, "get_license_key", lambda: "valid-key")

    response = client.post("/check_key", json={
        "key": "\ufeff valid\u200b-key \n",
        "version": "6.0",
    })

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_check_key_rejects_old_client_version(client, monkeypatch):
    monkeypatch.setattr(app_module.db, "get_license_key", lambda: "valid-key")
    monkeypatch.setattr(app_module.config, "MIN_CLIENT_VERSION", "6.0")

    response = client.post("/check_key", json={
        "key": "valid-key",
        "version": "5.0",
    })

    assert response.status_code == 200
    assert response.get_json()["status"] == "fail"
    assert "升级" in response.get_json()["msg"]


def test_check_key_rejects_missing_client_version(client, monkeypatch):
    monkeypatch.setattr(app_module.db, "get_license_key", lambda: "valid-key")

    response = client.post("/check_key", json={"key": "valid-key"})

    assert response.status_code == 400
    assert response.get_json()["status"] == "fail"


def test_database_rows_serialize_temporal_types():
    row = db._serialize_row({
        "date": datetime.date(2026, 9, 13),
        "begin": datetime.time(8, 0),
        "created_at": datetime.datetime(2026, 9, 13, 8, 1, 2),
    })

    assert row == {
        "date": "2026-09-13",
        "begin": "08:00",
        "created_at": "2026-09-13 08:01:02",
    }


