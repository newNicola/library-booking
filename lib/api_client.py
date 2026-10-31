"""
API client for Hebei Agricultural University library seat booking.

Provides synchronous wrappers around all REST endpoints.
All network calls use the ``requests`` library with persistent Session.
Cookie handling is automatic from cookies.json.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple, TypeAlias, Union

import requests

from .storage import DATA_DIR, read_sensitive_json, write_sensitive_json
from .sub_floor_fallback import get_fallback_sub_floors

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace"
COOKIES_FILE = str(DATA_DIR / "cookies.json")
PROFILE_FILE = str(DATA_DIR / "user_profile.json")
_LEGACY_USER_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.abspath(os.path.join(APP_DIR, ".."))
)
_LEGACY_COOKIES_FILE = os.path.join(_LEGACY_USER_DIR, "cookies.json")
_LEGACY_PROFILE_FILE = os.path.join(_LEGACY_USER_DIR, "user_profile.json")
log = logging.getLogger(__name__)
ApiStatus: TypeAlias = Union[bool, Literal["expired"]]


class SessionExpiredError(ValueError):
    """The upstream returned a login page or an empty unauthenticated response."""


class InvalidResponseError(ValueError):
    """The upstream response was neither valid JSON nor an authentication redirect."""

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL.split("/qljfwapp")[0],
    "Referer": f"{BASE_URL}/modules/myAppointment/index.do",
}

def _load_json(path: str) -> dict:
    return read_sensitive_json(path)

def _now_ts() -> str:
    return str(int(time.time() * 1000))


def _normalize_hhmm(value: str) -> str:
    parts = value.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return f"{value}:00"


def _resp_json(resp: requests.Response):
    """Parse JSON and turn HTML/login responses into an authentication signal."""
    try:
        text = resp.content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidResponseError("学校接口返回了无法解码的数据") from exc
    text = text.lstrip("\ufeff \t\r\n")
    response_url = str(getattr(resp, "url", "")).lower()
    prefix = text[:256].lower()
    if (
        not text
        or "authserver/login" in response_url
        or prefix.startswith("<!doctype html")
        or prefix.startswith("<html")
    ):
        raise SessionExpiredError("Cookie 已过期")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        content_type = getattr(resp, "headers", {}).get("Content-Type", "unknown")
        raise InvalidResponseError(f"学校接口返回非 JSON 数据 ({content_type})") from exc


def _decode_response_text(resp: requests.Response) -> str:
    try:
        return resp.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return resp.text


def _compact_response_text(text: str, limit: int = 220) -> str:
    compact = " ".join((text or "").replace("\ufeff", "").split())
    return compact[:limit]


def _looks_like_login_response(resp: requests.Response, text: str) -> bool:
    response_url = str(getattr(resp, "url", "")).lower()
    body = (text or "").lstrip("\ufeff \t\r\n")
    body_lower = body[:2000].lower()
    login_markers = (
        "authserver/login",
        "cas.hebau.edu.cn",
        "loginform",
        "统一身份认证",
        "用户登录",
        "请登录",
    )
    return (
        not body.strip()
        or "authserver/login" in response_url
        or any(marker in body_lower for marker in login_markers)
    )


def _stringify_message(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


class FloorInfo:
    PLACE_WID: str
    PLACE_NAME: str
    FLOOR_NUM: str
    WID: str

    def __init__(self, row: dict):
        self.PLACE_WID = row.get("PLACE_WID", "")
        self.PLACE_NAME = row.get("FLOOR_NUM", "")  # no PLACE_NAME in API; use FLOOR_NUM
        self.FLOOR_NUM = row.get("FLOOR_NUM", "")
        self.WID = row.get("WID", "")

    def __repr__(self):
        return f"Floor({self.FLOOR_NUM} wid={self.WID})"


class SeatInfo:
    WID: str
    SEAT_NUM: str
    IS_APPLIED: str

    def __init__(self, row: dict):
        self.WID = row.get("WID", "")
        self.SEAT_NUM = row.get("SEAT_NUM", "")
        self.IS_APPLIED = row.get("IS_APPLIED", "0")

    @property
    def is_available(self) -> bool:
        return self.IS_APPLIED == "0"

    def __repr__(self):
        return f"Seat({self.SEAT_NUM} status={self.IS_APPLIED})"


class ViolationInfo:
    violatedCount: int
    remainCount: int
    defaultPeriod: str

    def __init__(self, data: dict):
        self.violatedCount = data.get("violatedCount", 0)
        self.remainCount = data.get("remainCount", 3)
        self.defaultPeriod = data.get("defaultPeriod", "")


class AppointmentRecord:
    WID: str
    FLOOR_DISPLAY: str
    SEAT_DISPLAY: str
    BEGINNING_DATE: str
    ENDING_DATE: str
    IS_CANCELLED: str
    IS_VIOLATED: str
    CREATED_AT: str

    def __init__(self, row: dict):
        self.WID = row.get("WID", "")
        self.FLOOR_DISPLAY = row.get("FLOOR_ID_DISPLAY", "")
        self.SEAT_DISPLAY = row.get("SEAT_WID_DISPLAY", "")
        self.BEGINNING_DATE = row.get("BEGINNING_DATE", "")
        self.ENDING_DATE = row.get("ENDING_DATE", "")
        self.IS_CANCELLED = row.get("IS_CANCELLED_DISPLAY", "否")
        self.IS_VIOLATED = row.get("IS_VIOLATED_DISPLAY", "否")
        self.CREATED_AT = row.get("CREATED_AT", "")

    def __repr__(self):
        return f"Record({self.FLOOR_DISPLAY} {self.SEAT_DISPLAY} {self.BEGINNING_DATE})"


class APIClient:
    """Synchronous API client."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self.user_profile: Dict[str, str] = {}
        self._cookie_loaded = False
        self._session_lock = threading.RLock()

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Serialize access to requests.Session, which is shared by GUI workers."""
        with self._session_lock:
            return self.session.request(method, url, **kwargs)

    def _mark_expired(self) -> None:
        self._cookie_loaded = False

    def load_cookie(self) -> bool:
        source = COOKIES_FILE if os.path.exists(COOKIES_FILE) else _LEGACY_COOKIES_FILE
        if not os.path.exists(source):
            return False
        try:
            cookies_data = _load_json(source)
            # Playwright storage_state format: {"cookies": [{...}, ...]}
            if "cookies" in cookies_data:
                for c in cookies_data["cookies"]:
                    if c.get("domain") == "cas.hebau.edu.cn":
                        continue  # CAS cookies aren't needed
                    self.session.cookies.set(
                        c["name"], c["value"],
                        domain=".ehall.hebau.edu.cn",
                        path="/",
                    )
            else:
                # Legacy format: {"name": "value", ...}
                for name, value in cookies_data.items():
                    self.session.cookies.set(name, value, domain=".ehall.hebau.edu.cn")
            if source != COOKIES_FILE:
                try:
                    write_sensitive_json(COOKIES_FILE, cookies_data)
                except OSError:
                    log.warning("could not migrate legacy cookie file", exc_info=True)
            self._cookie_loaded = True
            return True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("failed to load cookie file %s: %s", source, exc)
            return False

    def load_profile(self) -> bool:
        source = PROFILE_FILE if os.path.exists(PROFILE_FILE) else _LEGACY_PROFILE_FILE
        if not os.path.exists(source):
            return False
        try:
            self.user_profile = _load_json(source)
            if source != PROFILE_FILE:
                try:
                    write_sensitive_json(PROFILE_FILE, self.user_profile)
                except OSError:
                    log.warning("could not migrate legacy profile file", exc_info=True)
            return True
        except (OSError, ValueError, TypeError) as exc:
            log.warning("failed to load profile file %s: %s", source, exc)
            return False

    def logout(self) -> None:
        """Clear the in-memory session and persisted login data."""
        self.session.cookies.clear()
        self.user_profile = {}
        self._cookie_loaded = False
        for path in {COOKIES_FILE, PROFILE_FILE, _LEGACY_COOKIES_FILE, _LEGACY_PROFILE_FILE}:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                log.warning("failed to remove login data %s", path, exc_info=True)

    # -- user info helpers --
    def get_user_id(self) -> str:
        return self.user_profile.get("USER_ID", "")

    def get_user_name(self) -> str:
        return self.user_profile.get("USER_NAME", "")

    def get_dept_name(self) -> str:
        return self.user_profile.get("DEPT_NAME", "")

    @property
    def place_name(self) -> str:
        return self.user_profile.get("PLACE_NAME", self.user_profile.get("DEPT_NAME", ""))

    @property
    def school_district_code(self) -> str:
        return self.user_profile.get("SCHOOL_DISTRICT_CODE", "1")

    @property
    def school_district(self) -> str:
        return self.user_profile.get("SCHOOL_DISTRICT", "东校区")

    @property
    def location(self) -> str:
        return self.user_profile.get("LOCATION", "")

    # -- API methods --

    def get_floors(self) -> Tuple[ApiStatus, Union[List[FloorInfo], str]]:
        url = f"{BASE_URL}/modules/myAppointment/getFloorData.do"
        try:
            resp = self._request("POST", url, timeout=15)
            resp.raise_for_status()
            data = _resp_json(resp)
            code = data.get("code")
            if code == "1001":
                return "expired", []
            if code != "0":
                msg = data.get("msg", data.get("message", ""))
                return False, f"code={code} msg={msg}"
            rows = data.get("datas", {}).get("getFloorData", {}).get("rows", [])
            return True, [FloorInfo(r) for r in rows]
        except SessionExpiredError:
            self._mark_expired()
            return "expired", []
        except (requests.RequestException, InvalidResponseError, TypeError) as exc:
            return False, f"exception: {exc}"

    def get_sub_floors(self, place_wid: str, date_str: str) -> Tuple[ApiStatus, List[dict]]:
        """Load live partition data, falling back to the last known built-in map."""
        url = f"{BASE_URL}/modules/myAppointment/getLimitFloorData.do"
        payload = {
            "PLACE_WID": place_wid,
            "PLACE_WID1": place_wid,
            "BEGINNING_DATE": f"{date_str} 08:00",
            "BEGINNING_DATE1": f"{date_str} 08:00",
            "ENDING_DATE": f"{date_str} 09:59",
            "ENDING_DATE1": f"{date_str} 09:59",
        }
        try:
            resp = self._request("POST", url, data=payload, timeout=15)
            resp.raise_for_status()
            data = _resp_json(resp)
            code = data.get("code")
            if code == "1001":
                return "expired", []
            rows = data.get("datas", {}).get("getLimitFloorData", {}).get("rows", [])
            if (code == "0" or code == 0) and rows:
                return True, rows
            log.warning("live sub-floor response was unusable; using fallback (code=%s)", code)
        except SessionExpiredError:
            self._mark_expired()
            return "expired", []
        except (requests.RequestException, InvalidResponseError, TypeError) as exc:
            log.warning("live sub-floor request failed; using fallback: %s", exc)

        # Last-known map for temporary upstream failures.
        return True, get_fallback_sub_floors(place_wid)

    def get_seats(self, place_wid: str, floor_num: str,
                   date_str: str, begin_time: str, end_time: str,
                   ) -> Tuple[ApiStatus, Union[List[SeatInfo], str]]:
        url = f"{BASE_URL}/api/getApplySeatDetailNew.do"
        payload = {
            "formData": json.dumps({
                "BEGINNING_DATE": f"{date_str} {_normalize_hhmm(begin_time)}",
                "ENDING_DATE": f"{date_str} {_normalize_hhmm(end_time)}",
                "PLACE_WID": place_wid,
                "FLOOR_NUM": floor_num,
            }),
        }
        try:
            resp = self._request("POST", url, data=payload, timeout=15)
            resp.raise_for_status()
            data = _resp_json(resp)
            code = data.get("code")
            if code == "1001":
                return "expired", []
            if code != "0" and code != 0:
                return False, []
            rows = data.get("data", [])
            return True, [SeatInfo(r) for r in rows]
        except SessionExpiredError:
            self._mark_expired()
            return "expired", []
        except (requests.RequestException, InvalidResponseError, TypeError) as exc:
            log.warning("seat request failed: %s", exc)
            return False, str(exc)

    def get_violations(self) -> Tuple[ApiStatus, Optional[ViolationInfo]]:
        url = f"{BASE_URL}/api/getViolated.do"
        try:
            resp = self._request("GET", url, timeout=15)
            resp.raise_for_status()
            data = _resp_json(resp)
            code = data.get("code")
            if code == "1001":
                return "expired", None
            if code != "0" and code != 0:
                return False, None
            return True, ViolationInfo(data)
        except SessionExpiredError:
            self._mark_expired()
            return "expired", None
        except (requests.RequestException, InvalidResponseError, TypeError) as exc:
            log.warning("violation request failed: %s", exc)
            return False, None

    def get_appointment_records(self, date_str: str, page: int = 1,
                                page_size: int = 10,
                                cancelled_filter: str = "") -> Tuple[ApiStatus, dict]:
        """Get appointment records for a given date.
        cancelled_filter: "" = all, "0" = not cancelled, "1" = cancelled
        Returns (ok, {"total": int, "rows": [AppointmentRecord, ...]})
        """
        url = f"{BASE_URL}/modules/myAppointment/getMyAppointmentRecord.do"
        filters = [{
            "name": "APPLY_DATE",
            "caption": "预约日期",
            "linkOpt": "AND",
            "builderList": "cbl_String",
            "builder": "equal",
            "value": date_str,
        }]
        if cancelled_filter in ("0", "1"):
            filters.append({
                "name": "IS_CANCELLED",
                "caption": "是否取消",
                "linkOpt": "AND",
                "builderList": "cbl_String",
                "builder": "equal",
                "value": cancelled_filter,
            })
        payload = {
            "querySetting": json.dumps(filters),
            "pageSize": str(page_size),
            "pageNumber": str(page),
        }
        try:
            resp = self._request("POST", url, data=payload, timeout=15)
            resp.raise_for_status()
            data = _resp_json(resp)
            code = data.get("code")
            if code == "1001":
                return "expired", {}
            if code != "0" and code != 0:
                return False, {}
            record_data = data.get("datas", {}).get("getMyAppointmentRecord", {})
            total = record_data.get("totalSize", 0)
            rows = [AppointmentRecord(r) for r in record_data.get("rows", [])]
            return True, {"total": total, "rows": rows}
        except SessionExpiredError:
            self._mark_expired()
            return "expired", {}
        except (requests.RequestException, InvalidResponseError, TypeError) as exc:
            return False, {"error": str(exc)}

    def cancel_appointment(self, wid: str, ending_date: str) -> Tuple[ApiStatus, str]:
        """Cancel an appointment. Returns (ok, message)."""
        url = f"{BASE_URL}/api/appointmentCancel.do"
        payload = {
            "formData": json.dumps({
                "WID": wid,
                "ENDING_DATE": ending_date,
            }),
        }
        try:
            resp = self._request("POST", url, data=payload, timeout=15)
            resp.raise_for_status()
            data = _resp_json(resp)
            code = data.get("code")
            if code == "1001":
                return "expired", "Cookie 已过期"
            msg = data.get("msg", "")
            ok = code == 0 or code == "0"
            if ok:
                return True, msg or "取消成功"
            # Surface the real reason instead of a generic failure
            if msg:
                return False, f"{msg}"
            return False, f"code={code} resp={json.dumps(data, ensure_ascii=False)[:300]}"
        except SessionExpiredError:
            self._mark_expired()
            return "expired", "Cookie 已过期"
        except (requests.RequestException, InvalidResponseError, TypeError) as exc:
            return False, str(exc)

    def cancel_appointments(self, records: List[dict]) -> Tuple[ApiStatus, str]:
        """Batch cancel appointments.

        ``records`` is a list of dicts each containing ``wid`` and
        ``ending_date``. Cancels each in turn and returns a summary.
        """
        ok_count = 0
        errors = []
        for rec in records:
            wid = rec.get("wid", "")
            ending_date = rec.get("ending_date", "")
            if not wid:
                errors.append("(缺 wid)")
                continue
            ok, msg = self.cancel_appointment(wid, ending_date)
            if ok == "expired":
                return "expired", "Cookie 已过期"
            if ok:
                ok_count += 1
            else:
                errors.append(f"{wid[:8]}… {msg}")
        if ok_count and not errors:
            return True, f"成功取消 {ok_count} 条"
        summary = f"成功取消 {ok_count} 条，失败 {len(errors)} 条"
        if errors:
            summary += " | " + "；".join(errors[:3])
        return False, summary

    def read_notice(self) -> bool:
        url = f"{BASE_URL}/modules/myAppointment/T_PUBLIC_PLACE_READ_SAVE.do"
        try:
            resp = self._request("POST", url, data={}, timeout=15)
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            log.warning("notice acknowledgement failed: %s", exc)
            return False

    def submit_booking(self, seat: SeatInfo,
                       place_wid: str, floor_wid: str, place_name: str,
                       date_str: str, begin_time: str, end_time: str,
                       ) -> Tuple[ApiStatus, str]:
        if not self._cookie_loaded:
            return False, "当前未登录，请先登录"
        if not self.get_user_id() or not self.get_user_name():
            return False, "用户信息不完整，请重新登录后再预约"
        if not seat or not seat.WID or not seat.SEAT_NUM:
            return False, "座位信息无效，请重新加载并选择座位"
        if not place_wid or not floor_wid or not date_str or not begin_time or not end_time:
            return False, "预约参数不完整，请重新选择日期、分区和时段"
        if not seat.is_available:
            return False, "所选座位当前不可用"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            begin = datetime.strptime(begin_time[:5], "%H:%M")
            end = datetime.strptime(end_time[:5], "%H:%M")
        except (TypeError, ValueError):
            return False, "日期或时段格式无效"
        if end <= begin:
            return False, "结束时间必须晚于开始时间"
        url = f"{BASE_URL}/api/appointmentSave.do"
        short_begin = dt.strftime("%m-%d") + " " + begin_time[:5]
        short_end = dt.strftime("%m-%d") + " " + end_time[:5]
        payload = {
            "formData": json.dumps({
                "WID": "",
                "USER_ID": self.get_user_id(),
                "USER_NAME": self.get_user_name(),
                "DEPT_CODE": self.user_profile.get("DEPT_CODE", ""),
                "DEPT_NAME": self.get_dept_name(),
                "PHONE_NUMBER": self.user_profile.get("PHONE_NUMBER", ""),
                "PALCE_ID": place_wid,
                "PALCE_ID_DISPLAY": self.place_name,
                "BEGINNING_DATE": f"{date_str} {begin_time[:5]}",
                "ENDING_DATE": f"{date_str} {end_time[:5]}",
                "SCHOOL_DISTRICT_CODE": self.school_district_code,
                "SCHOOL_DISTRICT": self.school_district,
                "LOCATION": self.location,
                "PLACE_NAME": self.place_name,
                "IS_CANCELLED": "0",
                "BEGINNING_DATE1": short_begin,
                "ENDING_DATE1": short_end,
                "FLOOR_ID": floor_wid,
                "SEAT_NUM": seat.SEAT_NUM,
                "SEAT_WID": seat.WID,
                "SYNC_SCHEDULE": "0",
            }),
        }
        try:
            resp = self._request("POST", url, data=payload, timeout=15)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            try:
                data = _resp_json(resp)
            except SessionExpiredError:
                self._mark_expired()
                return "expired", "Cookie 已过期"
            except (InvalidResponseError, ValueError):
                return False, f"Invalid JSON response: {resp.text[:200]}"
            ok = data.get("code") == 0 or data.get("code") == "0"
            msg = data.get("msg", "")
            if not ok:
                return False, msg if msg else f"code={data.get('code')}"
            return True, msg
        except Exception as ex:
            return False, str(ex)

    def close(self) -> None:
        with self._session_lock:
            self.session.close()
