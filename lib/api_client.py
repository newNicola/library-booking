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
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _now_ts() -> str:
    return str(int(time.time() * 1000))


def _normalize_hhmm(value: str) -> str:
    parts = value.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return f"{value}:00"


def _resp_json(resp: requests.Response):
    """Parse JSON from response, handling UTF-8 BOM robustly."""
    content = resp.content.lstrip()
    return json.loads(content.decode('utf-8-sig'))


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
            data = _resp_json(resp)
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
        # Static partition data — backend filters based on session state,
        # so we serve the complete statically known list instead.
        STATIC_SUB_FLOORS = [
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "39bd32fd4f3d417f9c787351200b3cd0",
                "FLOOR_NUM": "三层-西区-C区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3hgn29vj30th3ic23lli2b4g23qf3cu5521",
                "CZRQ": "2025-09-03 18:57:41",
                "IS_USE": "1",
                "PX": 2.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "0",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "d19b1a281d1e447d9d118de58c4c6628",
                "FLOOR_NUM": "二层-西区-A区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 28,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3f5n3t7d3ga63tul3t2t2kqp2ck52867551",
                "CZRQ": "2025-03-24 15:31:44",
                "IS_USE": "1",
                "PX": 4.0,
                "IS_PER_DISPLAY": "否"
            },
            {
                "IS_PER": "0",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "9eede20e61ea4c4a85ae31dd3035fc6b",
                "FLOOR_NUM": "二层-西区-D区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 32,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3f5n3t7d3ga63tul3t2t2kqp2ck52867551",
                "CZRQ": "2025-03-24 15:31:53",
                "IS_USE": "1",
                "PX": 4.0,
                "IS_PER_DISPLAY": "否"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "bf36f271125547538bbc0e02bdbbc9e5",
                "FLOOR_NUM": "二层-北区",
                "VERT_NUM": 10,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 12,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "2m6024cq2pah3auv37uf252c31ne26ss371",
                "CZRQ": "2025-03-24 15:32:02",
                "IS_USE": "1",
                "PX": 5.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "0",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "43ba1a9883ac409c947f7107520b7ae2",
                "FLOOR_NUM": "二层-东区-A区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "293l358s2tij3a1c229h2lj934gl28ou201",
                "CZRQ": "2025-03-24 15:30:26",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "否"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "0558e4243c8e4eeb84ed1d8f655a0b98",
                "FLOOR_NUM": "二层-东区-B区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3c1u3iq42npc378f20dv2vhh3qds39gf71",
                "CZRQ": "2025-03-24 15:30:18",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D931865113E06301120A0A7414",
                "FLOOR_NUM": "三层-西区-A区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 29,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3n292p1j2b4t3vuh3ctn2eev34lb2v6e311",
                "CZRQ": "2025-09-03 18:57:38",
                "IS_USE": "1",
                "PX": 2.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D931885113E06301120A0A7414",
                "FLOOR_NUM": "三层-西区-D区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 32,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3ji72e9533r12b4k3fvc37hj3ckn2i74881",
                "CZRQ": "2025-09-03 18:57:47",
                "IS_USE": "1",
                "PX": 2.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D931895113E06301120A0A7414",
                "FLOOR_NUM": "三层-北区",
                "VERT_NUM": 10,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 12,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "2jri3j9b282p3fji2kif3vqb357p2ojp711",
                "CZRQ": "2024-10-16 09:27:15",
                "IS_USE": "1",
                "PX": 3.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "0",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D9318A5113E06301120A0A7414",
                "FLOOR_NUM": "三层-东区-A区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 29,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "2s8m3hff32i826nh2qk031cb26et35a2351",
                "CZRQ": "2024-10-16 09:25:25",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "否"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D9318B5113E06301120A0A7414",
                "FLOOR_NUM": "三层-东区-B区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "23lh25i23idk2hce2f2t21ji3l8n2bhg21",
                "CZRQ": "2024-10-16 09:25:09",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D9318D5113E06301120A0A7414",
                "FLOOR_NUM": "三层-东区-C区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3dd72nt83hap35d53v8m39sg328f3kj6301",
                "CZRQ": "2024-10-16 09:25:42",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "0",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "227056D9318E5113E06301120A0A7414",
                "FLOOR_NUM": "三层-东区-D区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 32,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "22h72p8e2tj62ofh3mo629vn36s428np141",
                "CZRQ": "2024-10-16 09:25:51",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "否"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "befaea6c56c9461ea03aa35ccaff625a",
                "FLOOR_NUM": "三层-西区-B区",
                "VERT_NUM": 6,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "2beq3nfs30c13m6l3no033ss3vd123n8941",
                "CZRQ": "2025-09-03 19:02:40",
                "IS_USE": "1",
                "PX": 2.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "3a3612595f1c46cab72753ef42f0a7a7",
                "FLOOR_NUM": "二层-西区-B区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3f5n3t7d3ga63tul3t2t2kqp2ck52867551",
                "CZRQ": "2025-03-24 15:31:47",
                "IS_USE": "1",
                "PX": 4.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "df4ae4ea97584ae3b12994ae539e22a6",
                "FLOOR_NUM": "二层-东区-C区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "3g6o25ce2frs2ta330ih2sck32i83vti841",
                "CZRQ": "2025-03-24 15:30:37",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "是"
            },
            {
                "IS_PER": "0",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "0ef331778f1a4b8d873b6bc9effc33d7",
                "FLOOR_NUM": "二层-东区-D区",
                "VERT_NUM": 3,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 32,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "2mj22olb34tf36rb2ab43kej3jp529an641",
                "CZRQ": "2025-03-24 15:30:29",
                "IS_USE": "1",
                "PX": 1.0,
                "IS_PER_DISPLAY": "否"
            },
            {
                "IS_PER": "1",
                "PLACE_WID": "fb9dedd807fc48a59dc19338a50ea099",
                "WID": "1bb4a4c88dca4111bfa3310961112705",
                "FLOOR_NUM": "二层-西区-C区",
                "VERT_NUM": 9,
                "IS_USE_DISPLAY": "是",
                "CZR": "ampadmin",
                "HORI_NUM": 26,
                "CZZXM": "ampadmin",
                "FLOOR_DRAWING": "28ro3gk42smm3jk927hp3gkq3q0m20rr81",
                "CZRQ": "2025-03-24 15:31:50",
                "IS_USE": "1",
                "PX": 4.0,
                "IS_PER_DISPLAY": "是"
            },
        ]
        return True, STATIC_SUB_FLOORS

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
            data = _resp_json(resp)
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
            data = _resp_json(resp)
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
                data = _resp_json(resp)
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
