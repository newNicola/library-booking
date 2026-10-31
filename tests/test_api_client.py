import pytest

from lib.api_client import (
    APIClient,
    SeatInfo,
    SessionExpiredError,
    _normalize_hhmm,
    _resp_json,
)
from lib.sub_floor_fallback import get_fallback_sub_floors


class FakeResponse:
    def __init__(self, payload: bytes, status_code: int = 200):
        self.content = payload
        self.text = payload.decode("utf-8", errors="replace")
        self.status_code = status_code
        self.url = "https://ehall.hebau.edu.cn/api"
        self.headers = {"Content-Type": "application/json"}

    def raise_for_status(self):
        return None


def test_response_json_accepts_whitespace_and_repeated_bom():
    response = FakeResponse(b" \r\n\xef\xbb\xbf\xef\xbb\xbf{\"code\":\"0\"}")

    assert _resp_json(response) == {"code": "0"}


@pytest.mark.parametrize("payload", [b"", b"   \r\n", b"<!doctype html><html></html>"])
def test_response_json_recognizes_expired_session(payload):
    with pytest.raises(SessionExpiredError):
        _resp_json(FakeResponse(payload))


def test_normalize_hhmm():
    assert _normalize_hhmm("08:00:00") == "08:00"
    assert _normalize_hhmm("9") == "9:00"


def test_seat_availability():
    assert SeatInfo({"IS_APPLIED": "0"}).is_available
    assert not SeatInfo({"IS_APPLIED": "3"}).is_available


def test_fallback_sub_floors_are_scoped_to_place():
    rows = get_fallback_sub_floors("fb9dedd807fc48a59dc19338a50ea099")
    assert len(rows) == 18
    assert get_fallback_sub_floors("another-place") == []


def test_sub_floors_prefer_live_api(monkeypatch):
    client = APIClient()
    response = FakeResponse(
        b'{"code":"0","datas":{"getLimitFloorData":{"rows":'
        b'[{"PLACE_WID":"place","WID":"floor","FLOOR_NUM":"live"}]}}}'
    )
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: response)

    ok, rows = client.get_sub_floors("place", "2026-09-13")

    assert ok is True
    assert rows[0]["FLOOR_NUM"] == "live"


def test_batch_cancel_reports_complete_failure(monkeypatch):
    client = APIClient()
    monkeypatch.setattr(client, "cancel_appointment", lambda *_: (False, "upstream error"))

    ok, message = client.cancel_appointments([
        {"wid": "appointment-1", "ending_date": "2026-09-13 09:59"},
    ])

    assert ok is False
    assert "失败 1 条" in message


def test_batch_cancel_reports_partial_failure(monkeypatch):
    client = APIClient()
    outcomes = iter([(True, "ok"), (False, "busy")])
    monkeypatch.setattr(client, "cancel_appointment", lambda *_: next(outcomes))

    ok, message = client.cancel_appointments([
        {"wid": "appointment-1", "ending_date": "2026-09-13 09:59"},
        {"wid": "appointment-2", "ending_date": "2026-09-13 11:59"},
    ])

    assert ok is False
    assert "成功取消 1 条，失败 1 条" in message


