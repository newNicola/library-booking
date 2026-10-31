"""Application data paths and durable JSON writes."""

from __future__ import annotations

import json
import os
import base64
import tempfile
from pathlib import Path
from typing import Any


APP_NAME = "数图预约"


def get_data_dir() -> Path:
    """Return a writable per-user data directory."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = get_data_dir()


def atomic_write_json(path: os.PathLike[str] | str, data: Any) -> None:
    """Write JSON atomically so an interrupted save cannot corrupt the file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    """Protect/unprotect bytes for the current Windows user."""
    if os.name != "nt":
        return data

    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]

    source_buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    result = DataBlob()
    crypt32 = ctypes.windll.crypt32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = function(
        ctypes.byref(source),
        APP_NAME if protect else None,
        None,
        None,
        None,
        0x01,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(result),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(result.data)


def write_sensitive_json(path: os.PathLike[str] | str, data: Any) -> None:
    """Write sensitive JSON, encrypted for the current user on Windows."""
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if os.name == "nt":
        protected = _dpapi(raw, protect=True)
        atomic_write_json(path, {
            "format": "dpapi-v1",
            "payload": base64.b64encode(protected).decode("ascii"),
        })
    else:
        atomic_write_json(path, data)


def read_sensitive_json(path: os.PathLike[str] | str) -> Any:
    """Read encrypted JSON while retaining compatibility with legacy plaintext files."""
    with open(path, "r", encoding="utf-8-sig") as handle:
        stored = json.load(handle)
    if isinstance(stored, dict) and stored.get("format") == "dpapi-v1":
        payload = base64.b64decode(stored["payload"], validate=True)
        return json.loads(_dpapi(payload, protect=False).decode("utf-8"))
    return stored
