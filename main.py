#!/usr/bin/env python3
"""
数图预约 V6.0 - 河北农业大学图书馆座位预约工具

Entry point. Verifies license key, creates the APIClient, loads cookies/profile,
then launches the GUI.
"""

import sys

# Hide console window on Windows immediately after startup
if sys.platform == "win32":
    import ctypes
    try:
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE
    except Exception:
        pass

from lib.app_logging import configure_logging
from lib.gui import _build_main_app, _show_key_dialog

configure_logging()


def main() -> None:
    # Phase 1: show key dialog
    root = _show_key_dialog()
    if root is None:
        sys.exit(0)

    # Phase 2: build and run the main app reusing the same window
    app = _build_main_app(root)
    app.run()


if __name__ == "__main__":
    main()
