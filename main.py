#!/usr/bin/env python3
"""
数图预约 v2.0 - 河北农业大学图书馆座位预约工具

Entry point. Creates the APIClient, loads cookies/profile, then launches the GUI.
"""

import os
import sys

# Ensure the lib directory is on the path
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from gui import BookingApp


def main() -> None:
    app = BookingApp()
    app.run()


if __name__ == "__main__":
    main()
