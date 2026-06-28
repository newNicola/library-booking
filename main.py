#!/usr/bin/env python3
"""
数图预约 v2.0 - 河北农业大学图书馆座位预约工具

Entry point. Verifies license key, creates the APIClient, loads cookies/profile,
then launches the GUI.
"""

import os
import sys

# Ensure the lib directory is on the path
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from gui import BookingApp, _show_key_dialog, _build_main_app


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
