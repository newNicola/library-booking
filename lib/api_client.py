"""
API client for Hebei Agricultural University library seat booking.

Provides synchronous wrappers around all REST endpoints.
All network calls use the ``requests`` library with persistent Session.
Cookie handling is automatic from cookies.json.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace"
COOKIES_FILE = os.path.join(APP_DIR, "..", "cookies.json")
PROFILE_FILE = os.path.join(APP_DIR, "..", "user_profile.json")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL.split("/qljfwapp")[0],
    "Referer": f"{BASE_URL}/modules/myAppointment/index.do",
}

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _now_ts() -> str:
    return str(int(time.time() * 1000))


def _normalize_hhmm(value: str) -> str:
    parts = value.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return f"{value}:00"


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


class APIClient:
    """Synchronous API client."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self.user_profile: Dict[str, str] = {}
        self._cookie_loaded = False

    def load_cookie(self) -> bool:
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            cookies_data = _load_json(COOKIES_FILE)
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
            self._cookie_loaded = True
            return True
        except Exception:
            return False

    def load_profile(self) -> bool:
        if not os.path.exists(PROFILE_FILE):
            return False
        try:
            self.user_profile = _load_json(PROFILE_FILE)
            return True
        except Exception:
            return False

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

    def get_floors(self) -> Tuple[bool, List[FloorInfo]]:
        url = f"{BASE_URL}/modules/myAppointment/getFloorData.do"
        try:
            resp = self.session.post(url, timeout=15)
            data = resp.json()
            code = data.get("code")
            if code == "1001":
                return "expired", []
            if code != "0":
                msg = data.get("msg", data.get("message", ""))
                return False, f"code={code} msg={msg}"
            rows = data.get("datas", {}).get("getFloorData", {}).get("rows", [])
            return True, [FloorInfo(r) for r in rows]
        except Exception as exc:
            return False, f"exception: {exc}"

    def get_sub_floors(self, place_wid: str, date_str: str) -> Tuple[bool, List[dict]]:
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
            resp = self.session.post(url, data=payload, timeout=15)
            data = resp.json()
            code = data.get("code")
            if code == "1001":
                return "expired", []
            if code != "0" and code != 0:
                return False, []
            rows = data.get("datas", {}).get("getLimitFloorData", {}).get("rows", [])
            return True, rows
        except Exception:
            return False, []

    def get_seats(self, place_wid: str, floor_num: str,
                  date_str: str, begin_time: str, end_time: str,
                  ) -> Tuple[bool, List[SeatInfo]]:
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
            resp = self.session.post(url, data=payload, timeout=15)
            data = resp.json()
            code = data.get("code")
            if code == "1001":
                return "expired", []
            if code != "0" and code != 0:
                return False, []
            rows = data.get("data", [])
            return True, [SeatInfo(r) for r in rows]
        except Exception:
            return False, []

    def get_violations(self) -> Tuple[bool, Optional[ViolationInfo]]:
        url = f"{BASE_URL}/api/getViolated.do"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            code = data.get("code")
            if code == "1001":
                return "expired", None
            if code != "0" and code != 0:
                return False, None
            return True, ViolationInfo(data)
        except Exception:
            return False, None

    def read_notice(self) -> bool:
        url = f"{BASE_URL}/modules/myAppointment/T_PUBLIC_PLACE_READ_SAVE.do"
        try:
            self.session.post(url, data={}, timeout=15)
            return True
        except Exception:
            return False

    def submit_booking(self, seat: SeatInfo,
                       place_wid: str, floor_wid: str, place_name: str,
                       date_str: str, begin_time: str, end_time: str,
                       ) -> Tuple[bool, str]:
        url = f"{BASE_URL}/api/appointmentSave.do"
        dt = datetime.strptime(date_str, "%Y-%m-%d")
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
            resp = self.session.post(url, data=payload, timeout=15)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            try:
                data = resp.json()
            except ValueError:
                return False, f"Invalid JSON response: {resp.text[:200]}"
            ok = data.get("code") == 0 or data.get("code") == "0"
            msg = data.get("msg", "")
            if not ok:
                return False, msg if msg else f"code={data.get('code')}"
            return True, msg
        except Exception as ex:
            return False, str(ex)

    def close(self) -> None:
        self.session.close()
