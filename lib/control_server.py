"""Communication with the license, ban, and booking-log service."""

from __future__ import annotations

import logging
import os
import threading
import unicodedata
from typing import TYPE_CHECKING

import requests

from .api_client import _resp_json

if TYPE_CHECKING:
    from .api_client import APIClient, SeatInfo


log = logging.getLogger(__name__)
CONTROL_SERVER = os.environ.get("LIBRARY_CONTROL_SERVER", "http://154.8.220.29:5000").rstrip("/")
KEY_SERVER = f"{CONTROL_SERVER}/check_key"
HEALTH_SERVER = f"{CONTROL_SERVER}/health"
LOG_SERVER = f"{CONTROL_SERVER}/log_booking"
BAN_SERVER = f"{CONTROL_SERVER}/check_ban"
CLIENT_VERSION = "6.0"


def normalize_license_key(value: str) -> str:
    """Remove invisible/copy-paste characters from a license key."""
    return "".join(
        ch for ch in str(value or "")
        if not ch.isspace() and unicodedata.category(ch) != "Cf"
    )


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """Send a direct request to our control server without environment proxies."""
    session = requests.Session()
    session.trust_env = False
    return session.request(method, url, **kwargs)


def verify_key(key: str) -> tuple[bool, str]:
    normalized_key = normalize_license_key(key)
    if not normalized_key:
        return False, "请输入密钥"
    try:
        try:
            health_response = _request("GET", HEALTH_SERVER, timeout=5)
            if health_response.status_code >= 500:
                return False, f"验证服务器异常: HTTP {health_response.status_code}"
        except requests.Timeout:
            return False, f"验证服务器健康检查超时：{CONTROL_SERVER}"
        except requests.ConnectionError as exc:
            return False, f"无法直连验证服务器：{CONTROL_SERVER}；{exc}"

        response = _request(
            "POST", KEY_SERVER,
            json={"key": normalized_key, "version": CLIENT_VERSION},
            timeout=10,
        )
        data = _resp_json(response)
        if response.status_code >= 400:
            return False, data.get("msg") or f"服务器 HTTP {response.status_code}"
        if data.get("status") == "ok":
            return True, data.get("msg", "验证成功")
        return False, data.get("msg", "密钥无效")
    except requests.Timeout:
        return False, f"请求超时，请检查网络是否能访问 {CONTROL_SERVER}"
    except requests.ConnectionError:
        return False, f"无法连接验证服务器：{CONTROL_SERVER}"
    except (requests.RequestException, ValueError, TypeError) as exc:
        log.warning("key verification failed: %s", exc)
        return False, f"验证失败: {exc}；服务器：{CONTROL_SERVER}"


def is_banned(user_id: str) -> tuple[bool, str]:
    """Return ban state; retain the existing fail-open behavior on outages."""
    if not user_id:
        return False, ""
    try:
        response = _request("POST", BAN_SERVER, json={"user_id": user_id}, timeout=5)
        response.raise_for_status()
        data = _resp_json(response)
        if data.get("banned"):
            return True, data.get("msg", "该账号已被封禁，无法预约")
    except (requests.RequestException, ValueError, TypeError):
        log.warning("ban check failed; continuing in fail-open mode", exc_info=True)
    return False, ""


def report_booking(api: "APIClient", sub_floor: dict, seat: "SeatInfo",
                   date_str: str, begin: str, end: str) -> None:
    """Report a successful booking without blocking the booking workflow."""
    payload = {
        "user_id": api.get_user_id(),
        "user_name": api.get_user_name(),
        "dept_name": api.get_dept_name(),
        "place_name": api.place_name,
        "floor": sub_floor.get("FLOOR_NUM", "") if sub_floor else "",
        "seat": seat.SEAT_NUM,
        "date": date_str,
        "begin": begin,
        "end": end,
    }

    def send() -> None:
        try:
            response = _request("POST", LOG_SERVER, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException:
            log.warning("booking report failed", exc_info=True)

    threading.Thread(target=send, daemon=True).start()


