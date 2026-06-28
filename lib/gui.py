"""
GUI module for 数图预约 -- Hebei Agricultural University Library Seat Booker.

Built on tkinter + ttkbootstrap for modern themed widgets.
"""

import math
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

# Alias for shorter usage
MB = Messagebox

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_LIB_DIR)

import sys
sys.path.insert(0, _LIB_DIR)

from config import Config
from api_client import APIClient, FloorInfo, SeatInfo, ViolationInfo, AppointmentRecord, COOKIES_FILE, PROFILE_FILE, _resp_json


# ---------------------------------------------------------------------------
# Key Verification
# ---------------------------------------------------------------------------

_KEY_SERVER = "http://81.70.40.146:5000/check_key"


def verify_key(key: str) -> Tuple[bool, str]:
    """Send *key* to the remote server and return (success, message)."""
    try:
        resp = requests.post(_KEY_SERVER, json={"key": key}, timeout=10)
        data = _resp_json(resp)
        if data.get("status") == "ok":
            return True, data.get("msg", "验证成功")
        return False, data.get("msg", "密钥无效")
    except requests.exceptions.Timeout:
        return False, "请求超时，请检查网络连接"
    except requests.exceptions.ConnectionError:
        return False, "无法连接验证服务器"
    except Exception as exc:
        return False, f"验证失败: {exc}"


def _show_key_dialog():
    """Show key verification window. Returns the ttkb.Window on success, None on cancel."""
    root = ttkb.Window(themename="superhero", title="密钥验证")
    root.resizable(False, False)

    # Center on screen
    w, h = 380, 180
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    ttkb.Style().configure("Key.TLabel", font=("Microsoft YaHei", 10))
    ttkb.Style().configure("Key.TButton", font=("Microsoft YaHei", 10))

    frm = ttk.Frame(root, padding=20)
    frm.pack(fill=BOTH, expand=True)

    ttkb.Label(frm, text="请输入授权密钥以继续使用：", style="Key.TLabel").pack(pady=(0, 12))

    key_var = tk.StringVar()
    entry = ttkb.Entry(frm, textvariable=key_var, width=30, show="*")
    entry.pack(pady=5)
    entry.focus_set()

    result = {"ok": False}

    def _submit():
        k = key_var.get().strip()
        if not k:
            return
        ok, msg = verify_key(k)
        if ok:
            result["ok"] = True
            root.quit()  # exit mainloop without destroying window
        else:
            MB.show_error("验证失败", msg, parent=root)
            entry.delete(0, tk.END)
            entry.focus_set()

    def _on_enter(_e=None):
        _submit()

    entry.bind("<Return>", _on_enter)

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(pady=(15, 0))

    ttkb.Button(btn_frame, text="确定", command=_submit, style="Key.TButton").pack(side=tk.LEFT, padx=10)
    ttkb.Button(btn_frame, text="取消", command=root.destroy, style="Key.TButton").pack(side=tk.LEFT, padx=10)

    root.mainloop()

    if not result["ok"]:
        root.destroy()
        return None

    # Clear all key-dialog widgets so the root is ready for the main UI
    for child in root.winfo_children():
        child.destroy()
    root.resizable(True, True)
    return root


def _build_main_app(root) -> "BookingApp":
    """Build the main BookingApp reusing the existing root window."""
    app = object.__new__(BookingApp)
    app.root = root
    app.root.title("河北农业大学图书馆座位预约")

    # Center and resize the window
    w, h = 1000, 700
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    app.root.geometry(f"{w}x{h}+{x}+{y}")

    app.config = Config()
    app.api = APIClient()
    app.queue: queue.Queue = queue.Queue()
    app.threaded_api = ThreadedAPIClient(app.api, app.queue)

    app.mode = tk.StringVar(value="manual")
    app.floors: List[FloorInfo] = []
    app.sub_floors: List[dict] = []
    app.selected_sub_floor: Optional[dict] = None
    app.seats: List[SeatInfo] = []
    app.booking_in_progress = False
    app._multi_dates: List[str] = []
    app._multi_slots: List[dict] = []

    app._apply_theme(app.config.theme)
    app._build_ui()
    app._check_cookie()
    app.root.after(200, app._process_queue)
    app.root.bind_all("<<SeatSelected>>", lambda _e: app._sync_book_button_state())
    return app


# ---------------------------------------------------------------------------
# Threaded API wrapper
# ---------------------------------------------------------------------------

class ThreadedAPIClient:
    """Wraps APIClient so calls run in background threads, results go to a queue."""

    def __init__(self, api_client: APIClient, result_queue: queue.Queue) -> None:
        self._client = api_client
        self._queue = result_queue

    def load_cookie(self) -> bool:
        return self._client.load_cookie()

    def load_profile(self) -> bool:
        return self._client.load_profile()

    def get_user_id(self) -> str:
        return self._client.get_user_id()

    def get_user_name(self) -> str:
        return self._client.get_user_name()

    def _dispatch(self, fn: Callable, *args: Any,
                  result_tag: Optional[str] = None, **kwargs: Any) -> None:
        def _worker() -> None:
            try:
                result = fn(*args, **kwargs)
                if result_tag:
                    self._queue.put(("result", (result_tag, result)))
                else:
                    self._queue.put(("result", result))
            except Exception as exc:
                self._queue.put(("error", str(exc)))
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def async_get_floors(self) -> None:
        self._dispatch(self._client.get_floors, result_tag="floors")

    def async_get_seats(self, place_wid: str, floor_num: str,
                        date_str: str, begin: str, end: str) -> None:
        self._dispatch(self._client.get_seats, place_wid, floor_num, date_str, begin, end,
                       result_tag="seats")

    def async_check_violations(self) -> None:
        self._dispatch(self._client.get_violations, result_tag="violations")

    def async_get_sub_floors(self, place_wid: str, date_str: str) -> None:
        self._dispatch(self._client.get_sub_floors, place_wid, date_str, result_tag="sub_floors")

    def async_get_appointment_records(self, date_str: str, page: int = 1,
                                       page_size: int = 10,
                                       cancelled_filter: str = "") -> None:
        self._dispatch(self._client.get_appointment_records, date_str, page, page_size,
                       cancelled_filter, result_tag="records")

    def async_cancel_appointment(self, wid: str, ending_date: str) -> None:
        self._dispatch(self._client.cancel_appointment, wid, ending_date,
                       result_tag="cancel")


# ---------------------------------------------------------------------------
# Log Panel
# ---------------------------------------------------------------------------

class LogPanel(ttk.Frame):
    """Scrollable log text area."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        txt_frame = ttk.Frame(self)
        txt_frame.pack(side=TOP, fill=BOTH, expand=True, padx=5, pady=5)
        self.log_text = tk.Text(txt_frame, wrap=tk.WORD, state=tk.DISABLED,
                                font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        scrollbar = ttk.Scrollbar(txt_frame, orient=VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

    def append(self, msg: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def clear(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# Status Bar
# ---------------------------------------------------------------------------

class StatusBar(ttk.Frame):
    """Bottom status bar."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.violation_label = ttk.Label(self, text="违约: --", foreground="gray")
        self.step_label = ttk.Label(self, text="就绪", foreground="blue")
        self.status_label = ttk.Label(self, text="", foreground="black")
        self.by_label = ttk.Label(self, text="by nicola", foreground="gray", font=("Microsoft YaHei", 8))
        self.violation_label.pack(side=LEFT, padx=(5, 0))
        self.step_label.pack(side=LEFT, padx=(20, 0))
        self.status_label.pack(side=RIGHT, padx=(0, 5))
        self.by_label.pack(side=RIGHT, padx=(0, 5))

    def set_violations(self, remain: int, total: int) -> None:
        self.violation_label.config(text=f"违约剩余: {remain}/{total}")

    def set_step(self, step: str) -> None:
        self.step_label.config(text=step)

    def set_status(self, msg: str, color: str = "black") -> None:
        self.status_label.config(text=msg, foreground=color)


# ---------------------------------------------------------------------------
# Seat Grid Widget
# ---------------------------------------------------------------------------

class SeatGrid(ttk.Frame):
    """Displays seats as coloured buttons in a grid.

    Uses dynamic column count and optional vertical scrolling so that
    even very large seat inventories remain readable without going fullscreen.
    """

    # Thresholds
    MIN_COLS = 5
    MAX_COLS = 30
    TARGET_BTN_PX = 90          # desired button cell width including padding
    SCROLL_MIN_SEATS = 25       # enable scroll when visible seats exceed this
    SCROLL_MAX_ROWS = 18        # enable scroll if rows would exceed this

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._buttons: List[ttk.Button] = []
        self._selected_idx: int = -1
        self._seats: List[SeatInfo] = []
        self._visible_seats: List[SeatInfo] = []
        self._original_styles: Dict[int, str] = {}

        # Legend row
        leg = ttk.Frame(self)
        leg.pack(fill=X, padx=5, pady=(0, 3))
        ttk.Label(leg, text="■", foreground="green").pack(side=LEFT, padx=2)
        ttk.Label(leg, text="可选").pack(side=LEFT)
        ttk.Label(leg, text="■", foreground="red").pack(side=LEFT, padx=(10, 2))
        ttk.Label(leg, text="已约/不可用").pack(side=LEFT)
        ttk.Label(leg, text="■", foreground="orange").pack(side=LEFT, padx=(10, 2))
        ttk.Label(leg, text="我的").pack(side=LEFT)
        ttk.Label(leg, text="■", foreground="blue", font=("Microsoft YaHei", 8)).pack(side=LEFT, padx=(10, 2))
        ttk.Label(leg, text="选中", foreground="blue").pack(side=LEFT)

        self._grid_frame: ttk.Frame = ttk.Frame(self)
        self._grid_frame.pack(fill=BOTH, expand=True, padx=5, pady=3)
        self._scroll_canvas: Optional[tk.Canvas] = None
        self._scroll_frame: Optional[ttk.Frame] = None

    # -- helpers ----------------------------------------------------------

    def _compute_cols(self, num_seats: int) -> int:
        """Return the number of columns for *num_seats* visible seats."""
        # Start with a width-based estimate
        avail = self.winfo_width()
        if avail < 100:                       # widget not mapped yet
            avail = 900                        # reasonable default
        cols = max(self.MIN_COLS, avail // self.TARGET_BTN_PX)
        cols = min(cols, self.MAX_COLS)

        # If the resulting row count would be huge, force more columns
        rows = math.ceil(num_seats / cols) if cols else num_seats
        if rows > self.SCROLL_MAX_ROWS:
            cols = max(cols, math.ceil(num_seats / self.SCROLL_MAX_ROWS))
        cols = min(cols, self.MAX_COLS)
        return cols

    def _needs_scroll(self, num_seats: int, cols: int) -> bool:
        rows = math.ceil(num_seats / cols) if cols else 0
        return num_seats > self.SCROLL_MIN_SEATS or rows > self.SCROLL_MAX_ROWS

    def _destroy_grid_container(self) -> None:
        """Remove the old grid / scroll container so we can rebuild."""
        if self._scroll_canvas is not None:
            # Destroy the scrollbar+canvas parent frame together so the
            # scrollbar's yview command doesn't fire on a dead canvas.
            if self._scroll_canvas.winfo_exists():
                outer = self._scroll_canvas.master
                # Unbind events to avoid late callbacks
                self._scroll_canvas.unbind("<Configure>")
                outer.destroy()
            self._scroll_canvas = None
        if hasattr(self, '_scroll_frame') and self._scroll_frame is not None:
            self._scroll_frame = None  # already destroyed with outer
        if hasattr(self, '_grid_frame') and self._grid_frame is not None:
            self._grid_frame.destroy()
        if hasattr(self, '_grid_window_id'):
            del self._grid_window_id
        self._grid_frame = ttk.Frame(self)

    def _on_grid_configure(self, _event) -> None:
        """Callback: update canvas scrollregion when inner frame changes size."""
        if self._scroll_canvas is not None:
            self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _rebuild_container(self) -> None:
        """Clean up stale scroll/inner containers when toggling modes."""
        # Remove any scroll frame children from self
        for child in self._grid_frame.winfo_children():
            child.destroy()
        self._grid_frame.destroy()
        self._grid_frame = ttk.Frame(self)
        self._grid_frame.pack(fill=BOTH, expand=True, padx=5, pady=3)
        self._scroll_canvas = None
        self._scroll_frame = None
        if hasattr(self, '_grid_window_id'):
            del self._grid_window_id

    # -- public API -------------------------------------------------------

    def set_seats(self, seats: List[SeatInfo], show_only_available: bool = True) -> None:
        self._seats = seats
        filtered = seats if not show_only_available else [s for s in seats if s.is_available]
        # Sort by numeric portion of seat number, then lexicographically
        def _sort_key(s: SeatInfo) -> tuple:
            num = s.SEAT_NUM
            # Try parsing as int first so "002" < "010"
            try:
                return (0, int(num), "")
            except ValueError:
                return (1, 0, num)
        self._visible_seats = sorted(filtered, key=_sort_key)
        self._selected_idx = -1
        self._buttons = []
        self._original_styles = {}

        num = len(self._visible_seats)
        if num == 0:
            self._destroy_grid_container()
            self._grid_frame.pack(fill=BOTH, expand=True, padx=5, pady=3)
            return

        cols = self._compute_cols(num)
        do_scroll = self._needs_scroll(num, cols)

        self._destroy_grid_container()

        if do_scroll:
            # Build a scrollable container
            outer = ttk.Frame(self)
            outer.pack(fill=BOTH, expand=True, padx=5, pady=3)

            self._scroll_canvas = tk.Canvas(outer, highlightthickness=0)
            vsb = ttk.Scrollbar(outer, orient=VERTICAL, command=self._scroll_canvas.yview)
            inner = ttk.Frame(self._scroll_canvas)
            self._scroll_frame = inner

            self._scroll_canvas.configure(yscrollcommand=vsb.set)
            self._scroll_canvas.pack(side=LEFT, fill=BOTH, expand=True)
            vsb.pack(side=RIGHT, fill=Y)

            # Store the canvas window ID separately from _grid_frame
            self._grid_window_id = self._scroll_canvas.create_window((0, 0), window=inner, anchor="nw")
            # Make inner frame fill the canvas width when the window resizes
            self._scroll_canvas.bind("<Configure>",
                                     lambda _e: self._scroll_canvas.itemconfig(self._grid_window_id, width=max(1, _e.width)))
            # Update scroll region whenever the inner grid changes size
            inner.bind("<Configure>",
                       lambda _e: self._scroll_canvas.config(scrollregion=self._scroll_canvas.bbox("all")))

            # Mouse-wheel scrolling support
            def _on_mousewheel(event):
                if self._scroll_canvas is not None:
                    self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

            def _enter_scroll(_e):
                if self._scroll_canvas is not None:
                    self._scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel)

            def _leave_scroll(_e):
                if self._scroll_canvas is not None:
                    self._scroll_canvas.unbind_all("<MouseWheel>")

            self._scroll_canvas.bind("<Enter>", _enter_scroll)
            self._scroll_canvas.bind("<Leave>", _leave_scroll)

            self._grid_frame = inner
        else:
            self._grid_frame.pack(fill=BOTH, expand=True, padx=5, pady=3)

        # --- populate buttons -----------------------------------------------
        for idx, seat in enumerate(self._visible_seats):
            row, col = divmod(idx, cols)
            if seat.IS_APPLIED == "0":
                color = "green"
            elif seat.IS_APPLIED == "3":
                color = "orange"
            else:
                color = "red"

            style_name = ("Green.TButton" if color == "green"
                          else "Danger.TButton" if color == "red"
                          else "Warning.TButton")
            btn = ttk.Button(self._grid_frame, text=seat.SEAT_NUM, style=style_name,
                             command=lambda s=seat, i=idx: self._on_select(s, i))
            btn.grid(row=row, column=col, padx=2, pady=2, sticky=NSEW)
            self._buttons.append(btn)
            self._original_styles[idx] = style_name

        for c in range(cols):
            self._grid_frame.columnconfigure(c, weight=1)
        # Rows get equal weight too so they stretch vertically
        total_rows = math.ceil(num / cols)
        for r in range(total_rows):
            self._grid_frame.rowconfigure(r, weight=1)

    def _on_select(self, seat: SeatInfo, btn_idx: int) -> None:
        if 0 <= self._selected_idx < len(self._buttons):
            prev_style = self._original_styles.get(self._selected_idx, "Toolbutton")
            self._buttons[self._selected_idx].config(style=prev_style)
        self._selected_idx = btn_idx
        self._buttons[btn_idx].config(style="Success.TButton")
        # Notify parent so multi-day button state updates
        self.event_generate("<<SeatSelected>>", when="tail")

    @property
    def selected_seat(self) -> Optional[SeatInfo]:
        if self._selected_idx >= 0 and self._selected_idx < len(self._visible_seats):
            return self._visible_seats[self._selected_idx]
        return None

    @property
    def available_seats_count(self) -> int:
        return sum(1 for s in self._seats if s.is_available)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class BookingApp:
    """Main application window."""

    def __init__(self, root: Optional[tk.Tk] = None) -> None:
        self.root = root or ttkb.Window(themename="superhero")
        self.root.title("河北农业大学图书馆座位预约")
        self.root.geometry("1000x700")

        self.config = Config()
        self.api = APIClient()
        self.queue: queue.Queue = queue.Queue()
        self.threaded_api = ThreadedAPIClient(self.api, self.queue)

        self.mode = tk.StringVar(value="manual")
        self.floors: List[FloorInfo] = []
        self.sub_floors: List[dict] = []
        self.selected_sub_floor: Optional[dict] = None
        self.seats: List[SeatInfo] = []
        self.booking_in_progress = False
        self._multi_dates: List[str] = []
        self._multi_slots: List[dict] = []

        self._apply_theme(self.config.theme)
        self._build_ui()
        self._check_cookie()
        self.root.after(200, self._process_queue)
        # Bind seat-selection event for multi-day mode
        self.root.bind_all("<<SeatSelected>>", lambda _e: self._sync_book_button_state())

    def _apply_theme(self, theme_name: str) -> None:
        try:
            self.root.style.theme_use(theme_name)
        except Exception:
            pass

    def _check_cookie(self) -> None:
        ok = self.threaded_api.load_cookie() and self.threaded_api.load_profile()
        if not ok:
            self.user_label.config(text="用户: 未登录")
            self.log("未找到 Cookie，请先点击「刷新」登录")
            return
        self.user_label.config(text=f"用户: {self.threaded_api.get_user_name()} ({self.threaded_api.get_user_id()})")
        self.log(f"Cookie 已加载")
        self.threaded_api.async_check_violations()
        self._refresh_all()

    # -- browser-based cookie login --

    _LOGIN_URL = (
        "https://cas.hebau.edu.cn/authserver/login"
        "?service=https%3A%2F%2Fehall.hebau.edu.cn%2Flogin"
        "%3FportalService%3Dhttps%253A%252F%252Fehall.hebau.edu.cn%252Findex.html%2523%252F"
    )

    _APPOINTMENT_URL = (
        "https://ehall.hebau.edu.cn/qljfwapp/sys/lwAppointmentPublicPlace/"
        "index.do#/myAppointment"
    )

    def _open_browser_login(self, initial: bool = False) -> None:
        """Open Playwright-controlled Edge for login."""
        self.log("正在启动 Edge 浏览器...")
        self.status_bar.set_step("启动浏览器中...")
        threading.Thread(target=self._playwright_login_flow, daemon=True).start()

    def _playwright_login_flow(self) -> None:
        """Use Playwright + system Edge to let user login, then save cookies."""
        import json
        import subprocess
        import time

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.queue.put(("result", "Playwright 未安装，请在命令行执行: pip install playwright && playwright install"))
            return

        try:
            self.queue.put(("result", "正在启动 Playwright 驱动..."))
            pw = sync_playwright().start()

            self.queue.put(("result", "正在启动 Edge 浏览器..."))
            try:
                browser = pw.chromium.launch(channel="msedge", headless=False, timeout=15000)
            except Exception as launch_err:
                self.queue.put(("result", f"Edge 启动失败 ({launch_err})，尝试使用 Chromium..."))
                try:
                    browser = pw.chromium.launch(headless=False, timeout=15000)
                except Exception:
                    self.queue.put(("result", f"浏览器启动失败，请手动打开 Edge 访问登录页面"))
                    pw.stop()
                    return

            context = browser.new_context()
            page = context.new_page()
            self.queue.put(("result", "正在打开登录页面..."))
            try:
                page.goto(self._LOGIN_URL, timeout=20000)
            except Exception as nav_err:
                self.queue.put(("result", f"打开登录页面超时 ({nav_err})，请检查网络"))
                context.close()
                browser.close()
                pw.stop()
                return

            self.queue.put(("result", "请在浏览器中完成登录，最长等待 120 秒..."))
            self.root.after(0, lambda: self.status_bar.set_step("等待登录..."))

            # Poll for ehall cookies — only set after real authentication
            login_timeout = 120  # seconds
            poll_interval = 2    # seconds
            elapsed = 0
            logged_in = False
            while elapsed < login_timeout:
                time.sleep(poll_interval)
                elapsed += poll_interval
                try:
                    cookies = context.cookies()
                    ehall_cookies = [c for c in cookies if "ehall" in c.get("domain", "")]
                    if ehall_cookies:
                        logged_in = True
                        self.queue.put(("result", "检测到登录成功"))
                        break
                except Exception:
                    pass
                # Update countdown every 10 seconds
                if elapsed % 10 == 0:
                    remain = login_timeout - elapsed
                    self.root.after(0, lambda r=remain: self.status_bar.set_step(f"等待登录 ({r}s)..."))

            if not logged_in:
                self.queue.put(("result", "等待超时，请重新登录"))
                context.close()
                browser.close()
                pw.stop()
                return

            # Wait a moment for redirects to settle
            time.sleep(2)

            # Navigate to appointment page to get subsystem cookies
            self.queue.put(("result", "跳转到预约页面..."))
            try:
                page.goto(self._APPOINTMENT_URL, timeout=15000)
            except Exception:
                pass
            time.sleep(3)

            # Get cookies from Playwright context
            pw_cookies = context.cookies()

            # Build flat dict for ehall cookies
            cookies_flat = {}
            for c in pw_cookies:
                if "ehall" in c.get("domain", ""):
                    cookies_flat[c["name"]] = c["value"]

            if not cookies_flat:
                # Fallback: try storage_state
                storage = context.storage_state()
                for c in storage.get("cookies", []):
                    if "ehall" in c.get("domain", ""):
                        cookies_flat[c["name"]] = c["value"]

            if not cookies_flat:
                self.queue.put(("result", "未检测到登录 Cookie，请重试"))
                context.close()
                browser.close()
                pw.stop()
                return

            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies_flat, f, ensure_ascii=False, indent=2)

            # Extract user profile from the page DOM
            try:
                user_info_el = page.query_selector(".bh-headerBar-userInfo-detail")
                if user_info_el:
                    text = user_info_el.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    user_id = lines[0] if len(lines) > 0 else ""
                    user_name = lines[1] if len(lines) > 1 else ""
                    for ch in ["男", "女"]:
                        if user_name.endswith(ch):
                            user_name = user_name[:-1]
                            break
                    dept_name = lines[2] if len(lines) > 2 else ""
                else:
                    user_id = user_name = dept_name = ""

                profile = {
                    "USER_ID": user_id,
                    "USER_NAME": user_name,
                    "DEPT_CODE": "",
                    "DEPT_NAME": dept_name,
                    "PHONE_NUMBER": "",
                    "SCHOOL_DISTRICT_CODE": "1",
                    "SCHOOL_DISTRICT": "",
                    "LOCATION": "",
                    "PLACE_NAME": "",
                }

                with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                    json.dump(profile, f, ensure_ascii=False, indent=2)
                if user_id:
                    self.queue.put(("result", f"用户信息已保存: {user_name} ({user_id})"))
                else:
                    self.queue.put(("result", f"用户信息已保存 (学号未提取到，但可手动填写 {PROFILE_FILE}，不影响使用)"))
            except Exception as exc:
                self.queue.put(("result", f"提取用户信息失败: {exc}"))

            context.close()
            browser.close()
            pw.stop()

            self.queue.put(("result", f"Cookie 已保存 ({len(cookies_flat)} 项)"))
            self.root.after(0, self._reload_after_login)

        except ImportError:
            self.queue.put(("result", "Playwright 未安装"))
        except Exception as exc:
            self.queue.put(("result", f"Playwright 登录失败: {exc}"))

    def _reload_after_login(self) -> None:
        """Reload cookie/profile and refresh after successful login."""
        self.threaded_api.load_cookie()
        self.threaded_api.load_profile()
        self.user_label.config(text=f"用户: {self.threaded_api.get_user_name()} ({self.threaded_api.get_user_id()})")
        self.threaded_api.async_check_violations()
        self._refresh_all()

    # -- UI construction --

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=BOTH, expand=True)

        ttk.Label(main, text="河北农业大学图书馆座位预约系统",
                  font=("Microsoft YaHei", 16, "bold")).pack(pady=(0, 2))
        self.user_label = ttk.Label(main, text="", font=("Microsoft YaHei", 9), foreground="gray")
        self.user_label.pack(pady=(0, 8))

        # Mode
        mode_frame = ttk.LabelFrame(main, text="预约模式", padding=5)
        mode_frame.pack(fill=X, pady=(0, 8))
        ttk.Radiobutton(mode_frame, text="手动选座", variable=self.mode, value="manual",
                        command=self._on_mode_change).pack(side=LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="多天预约", variable=self.mode, value="multi",
                        command=self._on_mode_change).pack(side=LEFT, padx=5)

        # Controls
        ctrl = ttk.LabelFrame(main, text="预约设置", padding=5)
        ctrl.pack(fill=X, pady=(0, 8))

        # Partition
        ttk.Label(ctrl, text="分区:").pack(side=LEFT, padx=(0, 2))
        self.sub_floor_var = tk.StringVar()
        self.sub_floor_combo = ttk.Combobox(ctrl, textvariable=self.sub_floor_var, state="readonly", width=22)
        self.sub_floor_combo.pack(side=LEFT, padx=2)
        self.btn_refresh = ttk.Button(ctrl, text="刷新", command=self._refresh_all)
        self.btn_refresh.pack(side=LEFT, padx=2)

        # Date
        ttk.Label(ctrl, text="日期:").pack(side=LEFT, padx=(10, 2))
        self.date_var = tk.StringVar()
        self.date_combo = ttk.Combobox(ctrl, textvariable=self.date_var, state="readonly", width=14)
        self.date_combo.pack(side=LEFT, padx=2)
        self.date_label = ctrl.winfo_children()[-2]

        # Time
        ttk.Label(ctrl, text="时段:").pack(side=LEFT, padx=(10, 2))
        self.time_var = tk.StringVar()
        self.time_combo = ttk.Combobox(ctrl, textvariable=self.time_var, state="readonly", width=14)
        self.time_combo.pack(side=LEFT, padx=2)
        self.time_label = ctrl.winfo_children()[-2]

        # Populate
        dates = self.config.get_available_dates()
        self.date_combo["values"] = dates
        if dates:
            self.date_var.set(dates[0])
        self.time_combo["values"] = [s["label"] for s in self.config.time_slots]
        if self.config.time_slots:
            self.time_var.set(self.config.time_slots[0]["label"])

        # Trace for auto-reload
        self.time_var.trace_add("write", self._on_time_change)
        self.sub_floor_var.trace_add("write", self._on_sub_floor_change)
        self.date_var.trace_add("write", self._on_date_change)

        # Splitter: seats on top, log + buttons on bottom
        split = ttk.PanedWindow(main, orient=VERTICAL)
        split.pack(fill=BOTH, expand=True)

        # Top pane: seat grid
        top = ttk.Frame(split)
        self.seats_area = SeatGrid(top)
        self.seats_area.pack(fill=BOTH, expand=True)

        # Bottom pane: buttons + log
        bottom = ttk.Frame(split, height=160)
        bottom.pack_propagate(False)
        btn_frame = ttk.Frame(bottom)
        btn_frame.pack(fill=X, pady=(0, 4))
        self.btn_book = ttk.Button(btn_frame, text="预约", style="Success.TButton",
                                   command=self._on_book, state=tk.DISABLED)
        self.btn_book.pack(side=LEFT, padx=5)
        # Multi-day button — shown only in multi-day mode
        self.btn_multi_day = ttk.Button(btn_frame, text="一键约多天", style="Success.TButton",
                                        command=self._start_multi_day, state=tk.DISABLED)
        self.btn_multi_day.pack_forget()
        ttk.Button(btn_frame, text="设置", command=self._show_settings).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="预约记录", command=self._show_records).pack(side=LEFT, padx=5)

        self.log_panel = LogPanel(bottom)
        self.log_panel.pack(fill=BOTH, expand=True)

        split.add(top, weight=1)
        split.add(bottom, weight=0)

        # Status
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill=X, side=BOTTOM)

        self._on_mode_change()
        # Call once more after geometry settles so _sync_book_button_state sees real widths
        self.root.after(300, self._sync_book_button_state)

    # -- mode --

    def _on_mode_change(self) -> None:
        mode = self.mode.get()
        if mode == "multi":
            self.seats_area.pack(fill=BOTH, expand=True, pady=(0, 8))
            self.btn_book.pack_forget()
            self.btn_multi_day.pack(side=LEFT, padx=5)
            # Hide date/time dropdowns and labels — multi-day has its own picker
            self.date_label.pack_forget()
            self.date_combo.pack_forget()
            self.time_label.pack_forget()
            self.time_combo.pack_forget()
            # Reload seats using the first available time slot
            if self.sub_floor_var.get():
                dates = self.config.get_available_dates()
                first_date = dates[0] if dates else datetime.now().strftime("%Y-%m-%d")
                s = self.config.time_slots[0]
                self._load_seats_internal(self.sub_floor_var.get(), first_date, s["begin"], s["end"])
        else:
            self.seats_area.pack(fill=BOTH, expand=True, pady=(0, 8))
            self.btn_multi_day.pack_forget()
            self.date_label.pack(side=LEFT, padx=(10, 2))
            self.date_combo.pack(side=LEFT, padx=2)
            self.time_label.pack(side=LEFT, padx=(10, 2))
            self.time_combo.pack(side=LEFT, padx=2)
            self.btn_book.config(text="预约", style="Success.TButton")
            self.btn_book.pack(side=LEFT, padx=5)
        self._sync_book_button_state()

    # -- event handlers --

    def _on_time_change(self, *args: Any) -> None:
        for i, slot in enumerate(self.config.time_slots):
            if slot["label"] == self.time_var.get():
                self.config.set_auto_grab_time_slot_index(i)
                break
        if self.mode.get() == "manual" and self.sub_floor_var.get():
            self._load_seats()

    def _on_date_change(self, *args: Any) -> None:
        self._refresh_all()

    # -- multi-day booking --

    def _start_multi_day(self) -> None:
        """Multi-day mode: open date picker directly."""
        sub_floor = self.selected_sub_floor
        if not sub_floor:
            sub_floor_text = self.sub_floor_var.get()
            if not sub_floor_text:
                MB.show_error("提示", "请先选择分区")
                return
            for sf in self.sub_floors:
                if sf.get("FLOOR_NUM") == sub_floor_text:
                    sub_floor = sf
                    break
            if not sub_floor:
                MB.show_error("错误", "未找到分区信息")
                return

        self._multi_dates = []
        self._multi_slots = []
        self._show_multi_day_picker(sub_floor)

    def _show_multi_day_picker(self, sub_floor: dict) -> None:
        dlg = ttkb.Toplevel(title="选择日期范围")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.minsize(420, 480)

        dates = self.config.get_available_dates()

        # --- top label ---
        ttk.Label(dlg, text="已选座位后，选择时段并勾选日期：",
                  font=("Microsoft YaHei", 10, "bold")).pack(anchor=W, padx=15, pady=(15, 2))

        # --- time slot multi-selector ---
        ttk.Label(dlg, text="预约时段（可多选）：", font=("Microsoft YaHei", 9)).pack(anchor=W, padx=15, pady=(0, 2))
        slot_box = ttk.Frame(dlg)
        slot_box.pack(fill=X, padx=15, pady=(0, 5))
        slot_labels = [s["label"] for s in self.config.time_slots]
        slot_check_vars: List[tk.BooleanVar] = []
        for i, label in enumerate(slot_labels):
            var = tk.BooleanVar(value=(i == 0))  # default: first slot checked
            slot_check_vars.append(var)
            ttk.Checkbutton(slot_box, text=label, variable=var).pack(side=LEFT, padx=(0, 10))

        ttk.Label(dlg, text="⚠ 将对每个 日期 × 时段 的组合分别预约",
                  foreground="orange").pack(anchor=W, padx=15, pady=(0, 5))

        # --- bottom bar (pack first so it always reserves its space) ---
        bar = ttk.Frame(dlg, padding=(15, 8, 15, 12))
        bar.pack(fill=X, side=BOTTOM)

        # --- scrollable checkbox area (takes remaining space) ---
        canvas_frame = ttk.Frame(dlg)
        canvas_frame.pack(fill=BOTH, expand=True, padx=15, pady=(0, 5))

        canvas = tk.Canvas(canvas_frame, highlightthickness=0, height=200)
        vsb = ttk.Scrollbar(canvas_frame, orient=VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.config(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda _e: canvas.itemconfig(win_id, width=canvas.winfo_width()))

        # Mouse-wheel scrolling
        def _on_mw(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _enter_scroll(_e):
            canvas.bind_all("<MouseWheel>", _on_mw)
        def _leave_scroll(_e):
            canvas.unbind_all("<MouseWheel>")
        canvas.bind("<Enter>", _enter_scroll)
        canvas.bind("<Leave>", _leave_scroll)

        self._multi_vars: Dict[str, tk.BooleanVar] = {}
        for d in dates:
            var = tk.BooleanVar(value=False)
            self._multi_vars[d] = var
            ttk.Checkbutton(inner, text=d, variable=var).pack(anchor=W, pady=2, padx=2)

        def _select_all() -> None:
            for d in dates:
                self._multi_vars[d].set(True)

        def _select_weekdays() -> None:
            from datetime import datetime as dt
            for d in dates:
                wd = dt.strptime(d, "%Y-%m-%d").weekday()
                self._multi_vars[d].set(wd < 5)

        def _select_weekends() -> None:
            from datetime import datetime as dt
            for d in dates:
                wd = dt.strptime(d, "%Y-%m-%d").weekday()
                self._multi_vars[d].set(wd >= 5)

        def _confirm() -> None:
            selected = sorted([d for d in dates if self._multi_vars[d].get()])
            if not selected:
                MB.show_warning("提示", "请至少选择一个日期")
                return
            if not self.seats_area.selected_seat:
                MB.show_warning("提示", "请先在座位区点击选择座位")
                return
            # Collect selected time slots
            chosen_slots = []
            for i, var in enumerate(slot_check_vars):
                if var.get():
                    chosen_slots.append(self.config.time_slots[i])
            if not chosen_slots:
                MB.show_warning("提示", "请至少选择一个时段")
                return
            self._multi_dates = selected
            self._multi_slots = chosen_slots
            dlg.destroy()
            slot_names = ", ".join(s["label"] for s in chosen_slots)
            self.log(f"多天预约：{len(selected)} 天 × {len(chosen_slots)} 时段 — {', '.join(selected)}")
            self._sync_book_button_state()
            self._run_multi_day_booking(sub_floor)

        def _cancel() -> None:
            self._multi_dates = []
            dlg.destroy()
            self._sync_book_button_state()

        # Row 1: quick-select buttons (centered, with equal spacing)
        quick_frame = ttk.Frame(bar)
        quick_frame.pack(fill=X, pady=(0, 8))
        quick_frame.columnconfigure(0, weight=1)
        quick_frame.columnconfigure(1, weight=1)
        quick_frame.columnconfigure(2, weight=1)
        ttk.Button(quick_frame, text="全选", command=_select_all).grid(row=0, column=0, padx=2)
        ttk.Button(quick_frame, text="周一至周五", command=_select_weekdays).grid(row=0, column=1, padx=2)
        ttk.Button(quick_frame, text="周末", command=_select_weekends).grid(row=0, column=2, padx=2)

        # Row 2: confirm / cancel (centered)
        action_frame = ttk.Frame(bar)
        action_frame.pack(fill=X)
        inner_action = ttk.Frame(action_frame)
        inner_action.pack()
        ttk.Button(inner_action, text="确认", command=_confirm, style="Success.TButton").pack(side=LEFT, padx=4)
        ttk.Button(inner_action, text="取消", command=_cancel, style="Danger.TButton").pack(side=LEFT, padx=4)

    def _on_sub_floor_change(self, *args: Any) -> None:
        text = self.sub_floor_var.get()
        for sf in self.sub_floors:
            if sf.get("FLOOR_NUM") == text:
                self.selected_sub_floor = sf
                break
        if self.mode.get() == "multi":
            dates = self.config.get_available_dates()
            first_date = dates[0] if dates else datetime.now().strftime("%Y-%m-%d")
            s = self.config.time_slots[0]
            self._load_seats_internal(text, first_date, s["begin"], s["end"])
        else:
            self._load_seats()
        self._sync_book_button_state()

    # -- refresh (floors + sub-floors) --

    def _refresh_all(self) -> None:
        # If cookie not loaded yet, trigger Playwright login
        if not self.api._cookie_loaded:
            self.log("未登录，启动浏览器...")
            self._open_browser_login()
            return
        self.log("正在刷新...")
        self.status_bar.set_step("刷新中...")
        self.threaded_api.async_get_floors()

    def _load_seats(self) -> None:
        sub_floor_text = self.sub_floor_var.get()
        date_str = self.date_var.get()
        time_label = self.time_var.get()

        if not sub_floor_text or not date_str:
            return

        begin, end = "08:00", "12:00"
        for slot in self.config.time_slots:
            if slot["label"] == time_label:
                begin = slot["begin"]
                end = slot["end"]
                break
        self._load_seats_internal(sub_floor_text, date_str, begin, end)

    def _load_seats_internal(self, sub_floor_text: str, date_str: str, begin: str, end: str) -> None:
        place_wid = ""
        for sf in self.sub_floors:
            if sf.get("FLOOR_NUM") == sub_floor_text:
                place_wid = sf.get("PLACE_WID", "")
                self.selected_sub_floor = sf
                break
        if not place_wid:
            self.log("未找到分区信息，请刷新")
            return

        self.log(f"正在获取 {sub_floor_text} 座位...")
        self.status_bar.set_step("获取座位中...")
        self.btn_book.config(state=tk.DISABLED)
        self.threaded_api.async_get_seats(place_wid, sub_floor_text, date_str, begin, end)

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append(f"[{ts}] {msg}")

    # -- queue processor --

    def _process_queue(self) -> None:
        while True:
            try:
                item_type, data = self.queue.get_nowait()
            except queue.Empty:
                break
            if item_type == "result":
                self._handle_result(data)
            elif item_type == "error":
                self.log(f"错误: {data}")
                self._unlock_controls()
        self.root.after(200, self._process_queue)

    def _handle_result(self, result: Any) -> None:
        result_tags = {"floors", "sub_floors", "seats", "violations", "records", "cancel"}
        tag = ""
        if isinstance(result, tuple) and len(result) == 2 and result[0] in result_tags:
            tag, result = result

        if isinstance(result, tuple) and len(result) == 2:
            ok, data = result

            if tag == "seats":
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self._open_browser_login()
                    self._sync_book_button_state()
                    return
                if not ok:
                    self.seats = []
                    self.seats_area.set_seats([], self.config.show_only_available)
                    reason = data if isinstance(data, str) else "未知错误"
                    self.log(f"加载座位失败: {reason}")
                    self.status_bar.set_step("加载失败")
                    self._sync_book_button_state()
                    return
                if isinstance(data, list):
                    self.seats = data
                    avail = sum(1 for s in data if s.is_available)
                    self.seats_area.set_seats(data, self.config.show_only_available)
                    self.log(f"获取到 {len(data)} 个座位 (可用: {avail})")
                    self.status_bar.set_step("请选择座位" if data else "无座位")
                    self._sync_book_button_state()
                    return

            if tag == "violations":
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self._open_browser_login()
                elif ok and isinstance(data, ViolationInfo):
                    self.status_bar.set_violations(data.remainCount,
                                                   data.remainCount + data.violatedCount)
                    self.log(f"违约: 剩余 {data.remainCount} 次")
                else:
                    self.log("加载违约信息失败")
                return

            if tag == "records":
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self._open_browser_login()
                elif ok and isinstance(data, dict):
                    total = data.get("total", 0)
                    self.log(f"查询到 {total} 条预约记录")
                    if hasattr(self, '_records_update'):
                        self._records_update(data)
                else:
                    reason = data.get("error", "未知错误") if isinstance(data, dict) else str(data)
                    self.log(f"查询预约记录失败: {reason}")
                return

            if tag == "cancel":
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self._open_browser_login()
                elif ok:
                    self.log(f"取消成功: {data}")
                    if hasattr(self, '_records_refresh'):
                        self.root.after(500, self._records_refresh)
                else:
                    self.log(f"取消失败: {data}")
                return

            if tag == "floors" and (ok == "expired" or not ok or not data):
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self._open_browser_login()
                else:
                    self.floors = []
                    reason = data if isinstance(data, str) else ("无数据" if not ok else "响应为空")
                    self.log(f"加载场所失败: {reason}")
                self._sync_book_button_state()
                return

            if tag == "sub_floors" and (ok == "expired" or not ok or not data):
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self._open_browser_login()
                else:
                    self.sub_floors = []
                    self.sub_floor_combo["values"] = []
                    reason = data if isinstance(data, str) else ("无数据" if not ok else "响应为空")
                    self.log(f"加载分区失败: {reason}")
                    self.status_bar.set_step("加载失败" if not ok else "无分区")
                self._sync_book_button_state()
                return

            # Floors (list of FloorInfo)
            if isinstance(data, list) and data and isinstance(data[0], FloorInfo):
                self.floors = data
                if data:
                    date_str = self.date_var.get()
                    self.threaded_api.async_get_sub_floors(data[0].PLACE_WID, date_str)
                self.log(f"获取到 {len(data)} 个场所，加载分区中...")
                return

            # Sub-floors (list of dict with FLOOR_NUM + WID)
            if isinstance(data, list) and data and isinstance(data[0], dict) \
                    and "FLOOR_NUM" in data[0] and "WID" in data[0]:
                self.sub_floors = data
                self.sub_floor_combo["values"] = [sf["FLOOR_NUM"] for sf in data]
                if data:
                    self.sub_floor_var.set(data[0]["FLOOR_NUM"])
                    self.selected_sub_floor = data[0]
                self.log(f"获取到 {len(data)} 个分区")
                self.status_bar.set_step("请选择分区和日期")
                self._sync_book_button_state()
                return

            # Generic list of dicts — discard
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return

            # Seats (list of SeatInfo)
            if isinstance(data, list) and data and isinstance(data[0], SeatInfo):
                self.seats = data
                avail = sum(1 for s in data if s.is_available)
                self.seats_area.set_seats(data, self.config.show_only_available)
                self.log(f"获取到 {len(data)} 个座位 (可用: {avail})")
                self.status_bar.set_step("请选择座位")
                return

            # Violation
            if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], ViolationInfo):
                self.status_bar.set_violations(data[1].remainCount,
                                               data[1].remainCount + data[1].violatedCount)
                self.log(f"违约: 剩余 {data[1].remainCount} 次")
                return

            # Boolean
            if isinstance(data, bool):
                self.log("操作成功" if data else "操作失败")
                return

            # String
            if isinstance(data, str):
                if ok is False:
                    self.log(f"操作失败: {data}")
                else:
                    self.log(data)
                return

        self.log(f"收到结果: {result}")

    def _unlock_controls(self) -> None:
        if not self.booking_in_progress:
            self._sync_book_button_state()

    def _sync_book_button_state(self) -> None:
        if self.booking_in_progress:
            self.btn_book.config(state=tk.DISABLED)
            self.btn_multi_day.config(state=tk.DISABLED)
            return
        if self.mode.get() == "multi":
            ready = bool(self.sub_floor_var.get() and self.seats_area.selected_seat)
            self.btn_multi_day.config(state=tk.NORMAL if ready else tk.DISABLED)
        else:
            ready = self.seats_area.available_seats_count > 0
            self.btn_book.config(state=tk.NORMAL if ready else tk.DISABLED)

    # -- booking flow (manual) --

    def _on_book(self) -> None:
        if self.mode.get() == "multi":
            self._start_multi_day()
        else:
            self._submit_manual_booking()

    def _submit_manual_booking(self) -> None:
        seat = self.seats_area.selected_seat
        sub_floor = self.selected_sub_floor

        if not seat:
            MB.show_error("提示", "请先点击选择一个座位")
            return
        if not seat.is_available:
            MB.show_error("提示", "请选择可用的座位")
            return
        if not sub_floor:
            MB.show_error("提示", "请先选择分区")
            return

        time_label = self.time_var.get()
        begin, end = "08:00", "12:00"
        for slot in self.config.time_slots:
            if slot["label"] == time_label:
                begin = slot["begin"]
                end = slot["end"]
                break
        self._run_booking_flow(seat=seat, sub_floor=sub_floor,
                               date_str=self.date_var.get(), begin=begin, end=end)

    def _run_multi_day_booking(self, sub_floor: dict) -> None:
        seat = self.seats_area.selected_seat
        if seat is None:
            self.log("错误: 未选中座位")
            self._booking_finished()
            return
        slots = self._multi_slots
        dates = list(self._multi_dates)
        self._multi_pending: List[tuple] = []
        for d in dates:
            for slot in slots:
                self._multi_pending.append((d, slot["begin"], slot["end"]))
        self._multi_success = 0
        self._multi_fail = 0
        self._multi_total = len(self._multi_pending)

        self.booking_in_progress = True
        self.btn_book.config(state=tk.DISABLED)
        self.btn_multi_day.config(state=tk.DISABLED)
        self.status_bar.set_step(f"多天预约 0/{self._multi_total}...")
        self.log("=" * 40)
        self.log(f"多天预约: {sub_floor.get('FLOOR_NUM')} {seat.SEAT_NUM}")
        slot_names = ", ".join(s["label"] for s in slots)
        self.log(f"时段: {slot_names} | 日期: {', '.join(dates)} | 共 {self._multi_total} 次预约")
        self._process_next_multi(seat, sub_floor)

    def _process_next_multi(self, seat: SeatInfo, sub_floor: dict) -> None:
        if not self._multi_pending:
            self._booking_finished()
            self.log(f"多天预约完成: 成功 {self._multi_success}, 失败 {self._multi_fail}")
            return
        date_str, begin, end = self._multi_pending.pop(0)
        done = self._multi_total - len(self._multi_pending)
        self.status_bar.set_step(f"多天预约 {done}/{self._multi_total} — {date_str} {begin}-{end}")

        def _flow() -> None:
            try:
                api = self.api
                api.read_notice()
                ok, msg = api.submit_booking(seat, sub_floor["PLACE_WID"], sub_floor["WID"],
                                             sub_floor.get("FLOOR_NUM", ""), date_str, begin, end)
                if ok:
                    self._multi_success += 1
                    self.queue.put(("result", f"成功 {date_str} {begin}-{end} {msg}"))
                else:
                    self._multi_fail += 1
                    self.queue.put(("result", f"失败 {date_str} {begin}-{end} {msg or '未知错误'}"))
            except Exception as exc:
                self._multi_fail += 1
                self.queue.put(("result", f"异常 {date_str} {begin}-{end} {exc}"))
            finally:
                self.root.after(0, lambda: self._process_next_multi(seat, sub_floor))
        threading.Thread(target=_flow, daemon=True).start()

    def _run_booking_flow(self, seat: SeatInfo, sub_floor: dict,
                          date_str: str, begin: str, end: str) -> None:
        self.booking_in_progress = True
        self.btn_book.config(state=tk.DISABLED)
        self.status_bar.set_step("预约中...")
        self.log("=" * 40)
        self.log(f"预约: {sub_floor.get('FLOOR_NUM')} {seat.SEAT_NUM} {date_str} {begin}-{end}")

        def _flow() -> None:
            try:
                api = self.api
                self.queue.put(("result", "正在提交预约..."))
                ok, msg = api.submit_booking(seat, sub_floor["PLACE_WID"], sub_floor["WID"],
                                             sub_floor.get("FLOOR_NUM", ""), date_str, begin, end)
                if ok:
                    self.queue.put(("result", f"预约成功: {seat.SEAT_NUM} {date_str} {begin}-{end}"))
                else:
                    self.queue.put(("result", f"预约失败: {msg or '未知错误'}"))
            except Exception as exc:
                self.queue.put(("result", f"预约异常: {exc}"))
            finally:
                self.root.after(0, self._booking_finished)

        threading.Thread(target=_flow, daemon=True).start()

    def _booking_finished(self) -> None:
        self.booking_in_progress = False
        self._unlock_controls()
        self.status_bar.set_step("预约完成")

    @property
    def selected_seat(self) -> Optional[SeatInfo]:
        return self.seats_area.selected_seat

    # -- appointment records --

    def _show_records(self) -> None:
        dlg = ttkb.Toplevel(title="预约记录")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.minsize(700, 460)
        w, h = 780, 500
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        page_var = tk.IntVar(value=1)
        total_var = tk.IntVar(value=0)
        page_size = 10
        # Store record data keyed by tree item iid
        record_data: Dict[str, dict] = {}

        # --- top bar: date + filter + search ---
        top_bar = ttk.Frame(dlg, padding=(10, 8, 10, 4))
        top_bar.pack(fill=X)
        ttk.Label(top_bar, text="日期：").pack(side=LEFT)
        date_var = tk.StringVar()
        dates = self.config.get_available_dates()
        date_combo = ttk.Combobox(top_bar, textvariable=date_var, values=dates,
                                  state="readonly", width=14)
        date_combo.pack(side=LEFT, padx=2)
        if dates:
            date_var.set(dates[0])

        ttk.Label(top_bar, text="状态：").pack(side=LEFT, padx=(10, 0))
        filter_var = tk.StringVar(value="全部")
        filter_combo = ttk.Combobox(top_bar, textvariable=filter_var,
                                    values=["全部", "未取消", "已取消"],
                                    state="readonly", width=8)
        filter_combo.pack(side=LEFT, padx=2)

        def _get_filter_value() -> str:
            f = filter_var.get()
            if f == "未取消":
                return "0"
            elif f == "已取消":
                return "1"
            return ""

        def _load_records() -> None:
            d = date_var.get()
            if not d:
                return
            page_var.set(1)
            self.threaded_api.async_get_appointment_records(d, 1, page_size, _get_filter_value())
            self.log(f"正在查询 {d} 的预约记录...")

        ttk.Button(top_bar, text="查询", command=_load_records).pack(side=LEFT, padx=8)

        # --- treeview ---
        cols = ("floor", "seat", "begin", "end", "cancelled", "violated", "created")
        tree_frame = ttk.Frame(dlg, padding=(10, 0, 10, 0))
        tree_frame.pack(fill=BOTH, expand=True)
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14)
        headers = {
            "floor": "分区", "seat": "座位", "begin": "开始时间",
            "end": "结束时间", "cancelled": "已取消", "violated": "违约", "created": "创建时间"
        }
        widths = {"floor": 130, "seat": 80, "begin": 130, "end": 130,
                  "cancelled": 55, "violated": 55, "created": 130}
        for col in cols:
            tree.heading(col, text=headers[col])
            tree.column(col, width=widths[col], minwidth=50)
        vsb = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        # --- bottom bar: pagination + cancel button ---
        bot_bar = ttk.Frame(dlg, padding=(10, 4, 10, 8))
        bot_bar.pack(fill=X)
        page_label = ttk.Label(bot_bar, text="第 1 页 / 共 0 条")
        page_label.pack(side=LEFT)

        def _update_tree(result_data_in: dict) -> None:
            nonlocal record_data
            for item in tree.get_children():
                tree.delete(item)
            record_data.clear()
            total = result_data_in.get("total", 0)
            rows = result_data_in.get("rows", [])
            total_var.set(total)
            page = page_var.get()
            page_label.config(text=f"第 {page} 页 / 共 {total} 条")
            for r in rows:
                begin_short = r.BEGINNING_DATE[5:16] if len(r.BEGINNING_DATE) > 10 else r.BEGINNING_DATE
                end_short = r.ENDING_DATE[5:16] if len(r.ENDING_DATE) > 10 else r.ENDING_DATE
                created_short = r.CREATED_AT[5:16] if len(r.CREATED_AT) > 10 else r.CREATED_AT
                iid = tree.insert("", tk.END, values=(
                    r.FLOOR_DISPLAY, r.SEAT_DISPLAY,
                    begin_short, end_short,
                    r.IS_CANCELLED, r.IS_VIOLATED, created_short
                ))
                record_data[iid] = {"wid": r.WID, "ending_date": r.ENDING_DATE,
                                    "is_cancelled": r.IS_CANCELLED}

        def _prev_page() -> None:
            p = page_var.get()
            if p > 1:
                page_var.set(p - 1)
                self.threaded_api.async_get_appointment_records(
                    date_var.get(), p - 1, page_size, _get_filter_value())

        def _next_page() -> None:
            p = page_var.get()
            total_pages = max(1, (total_var.get() + page_size - 1) // page_size)
            if p < total_pages:
                page_var.set(p + 1)
                self.threaded_api.async_get_appointment_records(
                    date_var.get(), p + 1, page_size, _get_filter_value())

        def _cancel_selected() -> None:
            sel = tree.selection()
            if not sel:
                MB.show_warning("提示", "请先点击选择一条预约记录")
                return
            iid = sel[0]
            info = record_data.get(iid, {})
            if info.get("is_cancelled") == "是":
                MB.show_info("提示", "该预约已经取消")
                return
            wid = info.get("wid", "")
            ending_date = info.get("ending_date", "")
            if not wid:
                MB.show_error("错误", "未找到预约信息")
                return
            if not MB.show_question("确认取消", f"确定要取消这条预约吗？\n座位: {tree.item(iid, 'values')[1]}\n时间: {tree.item(iid, 'values')[2]} - {tree.item(iid, 'values')[3]}"):
                return
            self.threaded_api.async_cancel_appointment(wid, ending_date)
            self._records_refresh = _load_records
            self.log(f"正在取消预约 {wid}...")

        ttk.Button(bot_bar, text="取消预约", style="Danger.TButton",
                   command=_cancel_selected).pack(side=LEFT, padx=(20, 4))
        ttk.Button(bot_bar, text="下一页", command=_next_page).pack(side=RIGHT, padx=4)
        ttk.Button(bot_bar, text="上一页", command=_prev_page).pack(side=RIGHT, padx=4)

        # Store references for queue handler
        self._records_tree = tree
        self._records_update = _update_tree
        self._records_refresh = _load_records

        # Load initial data
        _load_records()

    # -- settings --

    def _show_settings(self) -> None:
        dlg = ttkb.Toplevel(title="设置")
        dlg.geometry("400x400")
        dlg.transient(self.root)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=15)
        frm.pack(fill=BOTH, expand=True)

        ttk.Label(frm, text="主题:").grid(row=0, column=0, sticky=W, pady=3)
        themes = ["superhero", "flatly", "cosmo", "minty", "pulse", "sandstone", "yeti"]
        theme_var = tk.StringVar(value=self.config.theme)
        ttk.Combobox(frm, textvariable=theme_var, values=themes, state="readonly", width=20).grid(row=0, column=1, pady=3)

        ttk.Label(frm, text="日期范围(天):").grid(row=1, column=0, sticky=W, pady=3)
        days_var = tk.IntVar(value=self.config.date_range_days)
        ttk.Spinbox(frm, from_=1, to=30, textvariable=days_var, width=18).grid(row=1, column=1, pady=3)

        avail_var = tk.BooleanVar(value=self.config.show_only_available)
        ttk.Checkbutton(frm, text="只显示可用座位", variable=avail_var).grid(row=3, column=0, columnspan=2, pady=3, sticky=W)

        def _save() -> None:
            self.config.set_theme(theme_var.get())
            self.config.set_date_range_days(days_var.get())
            self.config.set_show_only_available(avail_var.get())
            self._apply_theme(theme_var.get())
            new_dates = self.config.get_available_dates()
            self.date_combo["values"] = new_dates
            if new_dates:
                self.date_var.set(new_dates[0])
            MB.show_info("提示", "设置已保存")
            dlg.destroy()

        ttk.Button(frm, text="保存", command=_save, style="Success.TButton").grid(row=4, column=0, columnspan=2, pady=(15, 0))

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.api.close()
