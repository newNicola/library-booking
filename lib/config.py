"""
Configuration module for 数图预约 (Library Seat Booking App).

Handles default settings, loading/saving config.json, and providing
typed accessors for every user-adjustable parameter.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "date_range_days": 7,
    "time_slots": [
        {"label": "08:00-09:59", "begin": "08:00", "end": "09:59"},
        {"label": "10:00-11:59", "begin": "10:00", "end": "11:59"},
        {"label": "12:30-14:29", "begin": "12:30", "end": "14:29"},
        {"label": "14:30-16:19", "begin": "14:30", "end": "16:19"},
        {"label": "16:20-18:19", "begin": "16:20", "end": "18:19"},
        {"label": "18:20-20:19", "begin": "18:20", "end": "20:19"},
        {"label": "20:20-22:00", "begin": "20:20", "end": "22:00"},
    ],
    "auto_grab_interval_ms": 2000,
    "auto_grab_time_slot_index": 0,
    "preferred_floor_index": -1,
    "show_only_available": True,
    "window_width": 1000,
    "window_height": 700,
    "window_x": None,
    "window_y": None,
    "theme": "superhero",
}


def _load() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                saved: Dict[str, Any] = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(saved)
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def _save(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class Config:
    """Thread-safe-ish config accessor backed by a JSON file."""

    def __init__(self) -> None:
        self._data = _load()

    # -- getters --
    @property
    def date_range_days(self) -> int:
        return self._data.get("date_range_days", 7)

    @property
    def time_slots(self) -> List[Dict[str, str]]:
        return self._data.get("time_slots", DEFAULT_CONFIG["time_slots"])

    @property
    def auto_grab_interval_ms(self) -> int:
        return self._data.get("auto_grab_interval_ms", 2000)

    @property
    def auto_grab_time_slot_index(self) -> int:
        return self._data.get("auto_grab_time_slot_index", 0)

    @property
    def preferred_floor_index(self) -> int:
        return self._data.get("preferred_floor_index", -1)

    @property
    def show_only_available(self) -> bool:
        return self._data.get("show_only_available", True)

    @property
    def window_width(self) -> int:
        return self._data.get("window_width", 1000)

    @property
    def window_height(self) -> int:
        return self._data.get("window_height", 700)

    @property
    def window_x(self) -> Optional[int]:
        return self._data.get("window_x")

    @property
    def window_y(self) -> Optional[int]:
        return self._data.get("window_y")

    @property
    def theme(self) -> str:
        return self._data.get("theme", "superhero")

    # -- setters (persist immediately) --
    def set_date_range_days(self, value: int) -> None:
        self._data["date_range_days"] = value
        _save(self._data)

    def set_auto_grab_interval_ms(self, value: int) -> None:
        self._data["auto_grab_interval_ms"] = value
        _save(self._data)

    def set_auto_grab_time_slot_index(self, value: int) -> None:
        self._data["auto_grab_time_slot_index"] = value
        _save(self._data)

    def set_preferred_floor_index(self, value: int) -> None:
        self._data["preferred_floor_index"] = value
        _save(self._data)

    def set_show_only_available(self, value: bool) -> None:
        self._data["show_only_available"] = value
        _save(self._data)

    def set_theme(self, value: str) -> None:
        self._data["theme"] = value
        _save(self._data)

    def set_window_geometry(self, width: int, height: int, x: Optional[int], y: Optional[int]) -> None:
        self._data["window_width"] = width
        self._data["window_height"] = height
        self._data["window_x"] = x
        self._data["window_y"] = y
        _save(self._data)

    # -- helpers --
    def get_available_dates(self) -> List[str]:
        """Return list of YYYY-MM-DD strings for the next N days."""
        return [(datetime.now() + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(self.date_range_days)]

    def get_time_slot_label(self, index: int) -> str:
        slots = self.time_slots
        if 0 <= index < len(slots):
            return slots[index].get("label", "")
        return ""

    def get_time_slot_range(self, index: int) -> tuple:
        """Return (begin_str, end_str) for a time slot by index."""
        slots = self.time_slots
        if 0 <= index < len(slots):
            s = slots[index]
            return s["begin"], s["end"]
        return "08:00", "12:00"

    def reload(self) -> None:
        """Reload from disk (useful if config is edited externally)."""
        self._data = _load()
