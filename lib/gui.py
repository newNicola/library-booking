"""
GUI module for 数图预约 -- Hebei Agricultural University Library Seat Booker.

Built on tkinter + ttkbootstrap for modern themed widgets.
"""

import math
import logging
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Any, Dict, List, Optional

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

from .config import Config
from .api_client import APIClient, FloorInfo, SeatInfo, ViolationInfo, COOKIES_FILE, PROFILE_FILE
from .async_api import ThreadedAPIClient
from .control_server import is_banned, report_booking, verify_key
from .storage import write_sensitive_json


# Alias for shorter usage
MB = Messagebox
log = logging.getLogger(__name__)
APP_THEME = "flatly"
PALETTE = {
    "background": "#F5F7FA",
    "surface": "#FFFFFF",
    "text": "#1F2937",
    "muted": "#667085",
    "border": "#D9E0E8",
    "primary": "#356AE6",
    "primary_active": "#2858C7",
    "success": "#21875A",
    "warning": "#B26A16",
    "danger": "#C74652",
}


# ---------------------------------------------------------------------------
# Key Verification
# ---------------------------------------------------------------------------



def _show_key_dialog():
    """Show key verification window. Returns the ttkb.Window on success, None on cancel."""
    root = ttkb.Window(themename=APP_THEME, title="密钥验证")
    root.resizable(False, False)

    # Center on screen
    w, h = 440, 260
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    style = ttkb.Style()
    style.configure("KeyTitle.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
    root.configure(background=PALETTE["background"])
    style.configure("TFrame", background=PALETTE["background"])
    style.configure("TLabel", background=PALETTE["background"], foreground=PALETTE["text"])
    style.configure("KeyHint.TLabel", font=("Microsoft YaHei UI", 9), foreground=PALETTE["muted"])
    style.configure("Key.TLabel", font=("Microsoft YaHei UI", 9))
    style.configure("Key.TButton", font=("Microsoft YaHei UI", 9), padding=(14, 7))

    frm = ttk.Frame(root, padding=(28, 22))
    frm.pack(fill=BOTH, expand=True)

    ttkb.Label(frm, text="欢迎使用数图预约", style="KeyTitle.TLabel").pack(anchor=W)
    ttkb.Label(frm, text="请输入授权密钥以验证使用权限",
               style="KeyHint.TLabel").pack(anchor=W, pady=(2, 16))

    key_var = tk.StringVar()
    entry = ttkb.Entry(frm, textvariable=key_var, show="•", font=("Microsoft YaHei UI", 10))
    entry.pack(fill=X, ipady=5)
    entry.focus_set()

    reveal_var = tk.BooleanVar(value=False)

    def _toggle_reveal() -> None:
        entry.config(show="" if reveal_var.get() else "•")

    ttk.Checkbutton(frm, text="显示密钥", variable=reveal_var,
                    command=_toggle_reveal).pack(anchor=W, pady=(7, 0))

    result = {"ok": False}
    verify_results: queue.Queue = queue.Queue()

    status_var = tk.StringVar(value="")
    ttkb.Label(frm, textvariable=status_var, style="KeyHint.TLabel").pack(anchor=W, pady=(5, 0))

    def _poll_result() -> None:
        try:
            ok, msg = verify_results.get_nowait()
        except queue.Empty:
            root.after(50, _poll_result)
            return
        button.config(state=tk.NORMAL)
        entry.config(state=tk.NORMAL)
        status_var.set("")
        if ok:
            result["ok"] = True
            root.quit()
        else:
            MB.show_error("验证失败", msg, parent=root)
            entry.delete(0, tk.END)
            entry.focus_set()

    def _submit():
        k = key_var.get().strip()
        if not k:
            return
        button.config(state=tk.DISABLED)
        entry.config(state=tk.DISABLED)
        status_var.set("正在验证…")
        threading.Thread(
            target=lambda: verify_results.put(verify_key(k)),
            daemon=True,
        ).start()

    def _on_enter(_e=None):
        _submit()

    entry.bind("<Return>", _on_enter)

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(fill=X, pady=(14, 0))

    button = ttkb.Button(btn_frame, text="验证并继续", command=_submit, style="Key.TButton")
    button.pack(side=tk.RIGHT)
    ttkb.Button(btn_frame, text="取消", command=root.destroy,
                style="Key.TButton").pack(side=tk.RIGHT, padx=(0, 8))

    root.after(50, _poll_result)
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
    return BookingApp(root)


# ---------------------------------------------------------------------------
# Threaded API wrapper
# ---------------------------------------------------------------------------


class LogPanel(ttk.Frame):
    """Scrollable log text area."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        txt_frame = ttk.Frame(self)
        txt_frame.pack(side=TOP, fill=BOTH, expand=True)
        self.log_text = tk.Text(txt_frame, wrap=tk.WORD, state=tk.DISABLED,
                                font=("Microsoft YaHei UI", 9),
                                bg="#F8FAFC", fg="#344054",
                                insertbackground=PALETTE["primary"],
                                selectbackground="#DCE7FF",
                                relief=tk.FLAT, borderwidth=0,
                                highlightthickness=1, highlightbackground=PALETTE["border"],
                                padx=10, pady=8,
                                spacing1=1, spacing3=2)
        self.log_text.tag_configure("success", foreground=PALETTE["success"])
        self.log_text.tag_configure("error", foreground=PALETTE["danger"])
        self.log_text.tag_configure("warning", foreground=PALETTE["warning"])
        self.log_text.tag_configure("muted", foreground=PALETTE["muted"])
        scrollbar = ttk.Scrollbar(txt_frame, orient=VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

    def append(self, msg: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        lowered = msg.lower()
        if any(word in lowered for word in ("失败", "错误", "异常", "过期")):
            tag = "error"
        elif any(word in lowered for word in ("成功", "已保存", "已加载", "获取到")):
            tag = "success"
        elif any(word in lowered for word in ("等待", "正在", "请先", "提示")):
            tag = "warning"
        else:
            tag = "muted"
        self.log_text.insert(tk.END, msg + "\n", tag)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 400:
            self.log_text.delete("1.0", f"{line_count - 350}.0")
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
        self.violation_label = ttk.Label(self, text="违约额度  --", style="StatusMuted.TLabel")
        self.step_label = ttk.Label(self, text="●  就绪", style="StatusActive.TLabel")
        self.status_label = ttk.Label(self, text="", foreground=PALETTE["text"])
        self.by_label = ttk.Label(
            self, text="数图预约 · V6.0 · by nicola", style="StatusMuted.TLabel"
        )
        self.violation_label.pack(side=LEFT, padx=(14, 0), pady=7)
        self.step_label.pack(side=LEFT, padx=(22, 0), pady=7)
        self.status_label.pack(side=RIGHT, padx=(0, 14), pady=7)
        self.by_label.pack(side=RIGHT, padx=(0, 12), pady=7)

    def set_violations(self, remain: int, total: int) -> None:
        self.violation_label.config(text=f"违约额度  {remain}/{total}")

    def set_step(self, step: str) -> None:
        self.step_label.config(text=f"●  {step}")

    def set_status(self, msg: str, color: str = PALETTE["text"]) -> None:
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

        self._grid_frame: ttk.Frame = ttk.Frame(self)
        self._grid_frame.pack(fill=BOTH, expand=True, padx=2, pady=3)
        self._scroll_canvas: Optional[tk.Canvas] = None
        self._scroll_frame: Optional[ttk.Frame] = None
        self._empty_label: Optional[ttk.Label] = None

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

    def set_seats(
        self,
        seats: List[SeatInfo],
        show_only_available: bool = True,
        empty_message: Optional[str] = None,
    ) -> None:
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
            self._grid_frame.pack(fill=BOTH, expand=True, padx=2, pady=3)
            message = empty_message or (
                "当前条件下没有可用座位" if seats else "选择分区、日期和时段后显示座位"
            )
            self._empty_label = ttk.Label(
                self._grid_frame, text=f"◌\n{message}", style="Empty.TLabel", justify=CENTER
            )
            self._empty_label.pack(expand=True, pady=30)
            self.event_generate("<<SeatSelected>>", when="tail")
            return

        cols = self._compute_cols(num)
        do_scroll = self._needs_scroll(num, cols)

        self._destroy_grid_container()

        if do_scroll:
            # Build a scrollable container
            outer = ttk.Frame(self)
            outer.pack(fill=BOTH, expand=True, padx=5, pady=3)

            self._scroll_canvas = tk.Canvas(
                outer, highlightthickness=0, background=PALETTE["background"]
            )
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
                             command=lambda s=seat, i=idx: self._on_select(s, i),
                             state=tk.NORMAL if seat.is_available else tk.DISABLED)
            btn.grid(row=row, column=col, padx=3, pady=3, sticky=NSEW, ipady=3)
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
        self._buttons[btn_idx].config(style="Selected.TButton")
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
        self.root = root or ttkb.Window(themename=APP_THEME)
        self.root.title("河北农业大学图书馆座位预约")
        self.config = Config()
        width, height = self.config.window_width, self.config.window_height
        x = self.config.window_x
        y = self.config.window_y
        if x is None or y is None:
            x = max(0, (self.root.winfo_screenwidth() - width) // 2)
            y = max(0, (self.root.winfo_screenheight() - height) // 2)
        # Clamp restored geometry to the current display.  A saved geometry from
        # a larger monitor must not place controls outside a smaller screen.
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        min_width = min(820, max(620, screen_w - 40))
        min_height = min(580, max(480, screen_h - 80))
        width = min(max(width, min_width), max(min_width, screen_w - 20))
        height = min(max(height, min_height), max(min_height, screen_h - 40))
        x = min(max(0, x), max(0, screen_w - width))
        y = min(max(0, y), max(0, screen_h - height))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min_width, min_height)

        self.api = APIClient()
        self.queue: queue.Queue = queue.Queue()
        self.threaded_api = ThreadedAPIClient(self.api, self.queue)
        self._manual_time_labels: List[str] = []

        self.mode = tk.StringVar(value="manual")
        self.floors: List[FloorInfo] = []
        self.sub_floors: List[dict] = []
        self.selected_sub_floor: Optional[dict] = None
        self.seats: List[SeatInfo] = []
        self.booking_in_progress = False
        self._login_in_progress = False
        self._seat_request_id = 0
        self._multi_dates: List[str] = []
        self._multi_slots: List[dict] = []
        self._seat_reload_after_id: Optional[str] = None
        self._refresh_after_id: Optional[str] = None
        self._refreshing = False
        self._log_visible = True

        self._apply_theme(APP_THEME)
        self._build_ui()
        self._check_cookie()
        self.root.after(200, self._process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Bind seat-selection event for multi-day mode
        self.root.bind_all("<<SeatSelected>>", self._on_seat_selected)
        self.root.bind("<F5>", lambda _e: self._refresh_all())
        self.root.bind("<Control-Return>", lambda _e: self._on_book())

    def _on_close(self) -> None:
        try:
            self.config.set_window_geometry(
                self.root.winfo_width(),
                self.root.winfo_height(),
                self.root.winfo_x(),
                self.root.winfo_y(),
            )
        except Exception:
            log.warning("failed to persist window geometry", exc_info=True)
        self.root.destroy()

    def _apply_theme(self, theme_name: str) -> None:
        try:
            self.root.style.theme_use(theme_name)
        except Exception:
            log.warning("failed to apply theme %s", theme_name, exc_info=True)
        style = self.root.style
        font = "Microsoft YaHei UI"
        self.root.configure(background=PALETTE["background"])
        style.configure("TFrame", background=PALETTE["background"])
        style.configure(
            "TLabel", font=(font, 9),
            background=PALETTE["background"], foreground=PALETTE["text"],
        )
        style.configure(
            "TButton", font=(font, 9), padding=(10, 6),
            background=PALETTE["surface"], foreground=PALETTE["text"],
            bordercolor=PALETTE["border"], focuscolor=PALETTE["primary"],
        )
        style.map(
            "TButton",
            background=[("active", "#EAF0FF"), ("pressed", "#DCE7FF")],
            foreground=[("disabled", "#98A2B3")],
        )
        style.configure(
            "TCombobox", font=(font, 9), padding=5,
            fieldbackground=PALETTE["surface"], background=PALETTE["surface"],
            foreground=PALETTE["text"], bordercolor=PALETTE["border"],
            arrowcolor=PALETTE["muted"],
        )
        style.configure(
            "TCheckbutton", font=(font, 9),
            background=PALETTE["background"], foreground=PALETTE["text"],
        )
        style.configure(
            "TRadiobutton", font=(font, 9),
            background=PALETTE["background"], foreground=PALETTE["text"],
        )
        style.configure(
            "TLabelframe", background=PALETTE["background"],
            bordercolor=PALETTE["border"], relief=tk.SOLID,
        )
        style.configure(
            "TLabelframe.Label", font=(font, 10, "bold"),
            background=PALETTE["background"], foreground=PALETTE["text"],
        )
        style.configure("Title.TLabel", font=(font, 18, "bold"), foreground=PALETTE["text"])
        style.configure("Subtitle.TLabel", font=(font, 9), foreground=PALETTE["muted"])
        style.configure("Section.TLabel", font=(font, 11, "bold"), foreground=PALETTE["text"])
        style.configure("Meta.TLabel", font=(font, 9), foreground=PALETTE["muted"])
        style.configure(
            "Selection.TLabel", font=(font, 10, "bold"), foreground=PALETTE["primary"]
        )
        style.configure("Empty.TLabel", font=(font, 11), foreground=PALETTE["muted"])
        style.configure("StatusMuted.TLabel", font=(font, 8), foreground=PALETTE["muted"])
        style.configure("StatusActive.TLabel", font=(font, 8), foreground=PALETTE["primary"])
        style.configure("UserOnline.TLabel", font=(font, 9), foreground=PALETTE["success"])
        style.configure("UserOffline.TLabel", font=(font, 9), foreground=PALETTE["danger"])
        style.configure(
            "PrimaryWide.TButton", font=(font, 10, "bold"), padding=(20, 8),
            foreground="#FFFFFF", background=PALETTE["primary"],
            bordercolor=PALETTE["primary"],
        )
        style.map(
            "PrimaryWide.TButton",
            foreground=[("disabled", "#FFFFFF"), ("!disabled", "#FFFFFF")],
            background=[
                ("disabled", "#B8C4D8"),
                ("pressed", PALETTE["primary_active"]),
                ("active", PALETTE["primary_active"]),
            ],
        )
        style.configure("Selected.TButton", font=(font, 9, "bold"), padding=5,
                        foreground="#FFFFFF", background=PALETTE["primary"],
                        bordercolor=PALETTE["primary"])
        style.map("Selected.TButton", background=[("active", PALETTE["primary_active"])])
        style.configure(
            "Green.TButton", font=(font, 9), padding=5,
            foreground="#17653F", background="#E4F3EB", bordercolor="#A9D8C0",
        )
        style.map("Green.TButton", background=[("active", "#D5EBDD")])
        style.configure(
            "Danger.TButton", font=(font, 9), padding=5,
            foreground="#A63843", background="#FAE8EA", bordercolor="#E8B8BE",
        )
        style.map(
            "Danger.TButton",
            foreground=[("disabled", "#A86269")],
            background=[("disabled", "#F6DFE2")],
        )
        style.configure(
            "Warning.TButton", font=(font, 9), padding=5,
            foreground="#86500F", background="#FFF1DB", bordercolor="#E9C99C",
        )
        style.map(
            "Warning.TButton",
            foreground=[("disabled", "#987346")],
            background=[("disabled", "#FAECD7")],
        )
        style.configure(
            "Card.TLabelframe", padding=10,
            background=PALETTE["background"], bordercolor=PALETTE["border"],
        )
        style.configure(
            "Card.TLabelframe.Label", font=(font, 10, "bold"),
            background=PALETTE["background"], foreground=PALETTE["text"],
        )

    def _check_cookie(self) -> None:
        ok = self.threaded_api.load_cookie() and self.threaded_api.load_profile()
        if not ok:
            self.user_label.config(text="●  未登录", style="UserOffline.TLabel")
            self.log("未找到 Cookie，请先点击「刷新」登录")
            return
        self._update_user_label()
        self.log("Cookie 已加载")
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
        if self._login_in_progress:
            self.log("登录窗口已在打开，请在浏览器中完成登录")
            return
        self._login_in_progress = True
        self.log("正在启动 Edge 浏览器...")
        self.status_bar.set_step("启动浏览器中...")

        def worker() -> None:
            try:
                self._playwright_login_flow()
            finally:
                self.queue.put(("login_finished", None))

        threading.Thread(target=worker, daemon=True).start()

    def _playwright_login_flow(self) -> None:
        """Use Playwright + system Edge to let user login, then save cookies."""
        import time

        pw = None
        browser = None
        context = None

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
                    self.queue.put(("result", "浏览器启动失败，请手动打开 Edge 访问登录页面"))
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
                    log.debug("browser context was not ready while polling", exc_info=True)
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
                log.warning("appointment page navigation failed", exc_info=True)
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

            write_sensitive_json(COOKIES_FILE, cookies_flat)

            # Extract user profile from the page DOM
            try:
                user_info_el = page.query_selector(".bh-headerBar-userInfo-detail")
                if user_info_el:
                    text = user_info_el.inner_text()
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
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

                write_sensitive_json(PROFILE_FILE, profile)
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
            log.exception("Playwright login failed")
            self.queue.put(("result", f"Playwright 登录失败: {exc}"))
        finally:
            for resource, close_name in (
                (context, "close"),
                (browser, "close"),
                (pw, "stop"),
            ):
                if resource is None:
                    continue
                try:
                    getattr(resource, close_name)()
                except Exception:
                    log.debug("Playwright resource cleanup failed", exc_info=True)

    def _reload_after_login(self) -> None:
        """Reload cookie/profile and refresh after successful login."""
        self._login_in_progress = False
        self.threaded_api.load_cookie()
        self.threaded_api.load_profile()
        self._update_user_label()
        self.threaded_api.async_check_violations()
        self._refresh_all()

    # -- UI construction --

    def _update_user_label(self) -> None:
        name = self.threaded_api.get_user_name() or "已登录用户"
        user_id = self.threaded_api.get_user_id()
        suffix = f" · {user_id}" if user_id else ""
        self.user_label.config(text=f"●  {name}{suffix}", style="UserOnline.TLabel")

    def _logout(self) -> None:
        if self._login_in_progress or self.booking_in_progress:
            MB.show_warning("当前操作尚未完成，请稍后再退出登录", "提示")
            return
        self.api.logout()
        self._seat_request_id += 1
        self.floors = []
        self.sub_floors = []
        self.selected_sub_floor = None
        self.seats = []
        self.sub_floor_var.set("")
        self.date_var.set("")
        self.time_var.set("")
        self.seats_area.set_seats([], self.config.show_only_available, empty_message="登录后显示座位")
        self.user_label.config(text="●  未登录", style="UserOffline.TLabel")
        self.seat_count_var.set("请先登录")
        self._update_selection_summary()
        self._sync_book_button_state()
        self.log("已退出登录，登录数据已清除")

    def _validate_booking_ready(self) -> Optional[str]:
        if not self.api._cookie_loaded:
            return "当前未登录，请先登录"
        if not self.api.get_user_id() or not self.api.get_user_name():
            return "用户信息未加载完整，请重新登录后再预约"
        if not self.selected_sub_floor:
            return "请先选择分区"
        seat = self.seats_area.selected_seat
        if not seat:
            return "请先选择座位"
        if not seat.is_available:
            return "请选择可用的座位"
        if not self.date_var.get():
            return "请先选择日期"
        if not self._selected_time_slots():
            return "请至少选择一个时段"
        return None

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        main.pack(fill=BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=X, pady=(0, 12))
        heading = ttk.Frame(header)
        heading.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(heading, text="数图预约", style="Title.TLabel").pack(anchor=W)
        ttk.Label(heading, text="河北农业大学图书馆座位预约助手",
                  style="Subtitle.TLabel").pack(anchor=W, pady=(1, 0))
        header_actions = ttk.Frame(header)
        header_actions.pack(side=RIGHT)
        self.user_label = ttk.Label(
            header_actions, text="", width=18, anchor=E,
            style="UserOffline.TLabel",
        )
        self.user_label.pack(side=LEFT, padx=(0, 14))
        self.logout_button = ttk.Button(header_actions, text="退出登录", command=self._logout)
        self.logout_button.pack(side=LEFT, padx=3)
        ttk.Button(header_actions, text="预约记录", command=self._show_records).pack(side=LEFT, padx=3)
        ttk.Button(header_actions, text="设置", command=self._show_settings).pack(side=LEFT, padx=3)

        ctrl = ttk.LabelFrame(main, text="预约条件", padding=(12, 8), style="Card.TLabelframe")
        ctrl.pack(fill=X, pady=(0, 10))
        for column in (1, 3, 5):
            ctrl.columnconfigure(column, weight=1, minsize=90)
        ctrl.columnconfigure(1, weight=2)
        ctrl.columnconfigure(3, weight=1)
        ctrl.columnconfigure(5, weight=1)

        ttk.Label(ctrl, text="模式", style="Meta.TLabel").grid(row=0, column=0, sticky=W, pady=(0, 4))
        mode_frame = ttk.Frame(ctrl)
        mode_frame.grid(row=1, column=0, sticky=W, padx=(0, 18))
        ttk.Radiobutton(mode_frame, text="单日", variable=self.mode, value="manual",
                        command=self._on_mode_change).pack(side=LEFT)
        ttk.Radiobutton(mode_frame, text="多天", variable=self.mode, value="multi",
                        command=self._on_mode_change).pack(side=LEFT, padx=(10, 0))

        ttk.Label(ctrl, text="分区", style="Meta.TLabel").grid(row=0, column=1, sticky=W, pady=(0, 4))
        self.sub_floor_var = tk.StringVar()
        self.sub_floor_combo = ttk.Combobox(ctrl, textvariable=self.sub_floor_var, state="readonly", width=22)
        self.sub_floor_combo.grid(row=1, column=1, sticky=EW, padx=(0, 18))

        self.date_label = ttk.Label(ctrl, text="日期", style="Meta.TLabel")
        self.date_label.grid(row=0, column=3, sticky=W, pady=(0, 4))
        self.date_var = tk.StringVar()
        self.date_combo = ttk.Combobox(ctrl, textvariable=self.date_var, state="readonly", width=14)
        self.date_combo.grid(row=1, column=3, sticky=EW, padx=(0, 18))

        self.time_label = ttk.Label(ctrl, text="时段", style="Meta.TLabel")
        self.time_label.grid(row=0, column=5, sticky=W, pady=(0, 4))
        self.time_var = tk.StringVar()
        self.time_button = ttk.Button(ctrl, textvariable=self.time_var, command=self._show_manual_time_picker)
        self.time_button.grid(row=1, column=5, sticky=EW, padx=(0, 18))
        self.btn_refresh = ttk.Button(ctrl, text="刷新  F5", command=self._refresh_all)
        self.btn_refresh.grid(row=1, column=6, sticky=E)

        # Populate
        dates = self.config.get_available_dates()
        self.date_combo["values"] = dates
        if dates:
            self.date_var.set(dates[0])
        if self.config.time_slots:
            index = min(
                max(0, self.config.auto_grab_time_slot_index),
                len(self.config.time_slots) - 1,
            )
            self._manual_time_labels = [self.config.time_slots[index]["label"]]
            self._sync_manual_time_summary()

        # Trace for auto-reload
        self.sub_floor_var.trace_add("write", self._on_sub_floor_change)
        self.date_var.trace_add("write", self._on_date_change)

        # Splitter: seats on top, activity log below
        split = ttk.PanedWindow(main, orient=VERTICAL)
        split.pack(fill=BOTH, expand=True)

        # Top pane: seat grid and primary action
        top = ttk.Frame(split)
        seat_header = ttk.Frame(top)
        seat_header.pack(fill=X, pady=(0, 5))
        ttk.Label(seat_header, text="选择座位", style="Section.TLabel").pack(side=LEFT)
        self.seat_count_var = tk.StringVar(value="尚未加载座位")
        ttk.Label(seat_header, textvariable=self.seat_count_var,
                  style="Meta.TLabel").pack(side=LEFT, padx=(12, 0))
        self.show_available_var = tk.BooleanVar(value=self.config.show_only_available)
        ttk.Checkbutton(
            seat_header, text="仅显示可用", variable=self.show_available_var,
            command=self._on_available_filter_change,
        ).pack(side=RIGHT)
        legend = ttk.Frame(top)
        legend.pack(fill=X, pady=(0, 6))
        for marker, label, color in (
            ("●", "可选", PALETTE["success"]),
            ("●", "不可用", PALETTE["danger"]),
            ("●", "我的预约", PALETTE["warning"]),
            ("●", "当前选中", PALETTE["primary"]),
        ):
            ttk.Label(legend, text=marker, foreground=color).pack(side=LEFT, padx=(0, 3))
            ttk.Label(legend, text=label, style="Meta.TLabel").pack(side=LEFT, padx=(0, 12))
        self.seats_area = SeatGrid(top)

        action_bar = ttk.Frame(top, padding=(0, 8, 0, 4))
        action_bar.pack(side=BOTTOM, fill=X)
        summary = ttk.Frame(action_bar)
        self.selection_var = tk.StringVar(value="请选择一个可用座位")
        ttk.Label(summary, textvariable=self.selection_var,
                  style="Selection.TLabel").pack(anchor=W)
        self.selection_hint_var = tk.StringVar(value="选中后即可提交预约")
        ttk.Label(summary, textvariable=self.selection_hint_var,
                  style="Meta.TLabel").pack(anchor=W, pady=(2, 0))
        primary_actions = ttk.Frame(action_bar)
        primary_actions.pack(side=RIGHT, padx=(16, 0))
        summary.pack(side=LEFT, fill=X, expand=True)
        self.btn_book = ttk.Button(primary_actions, text="预约当前座位", style="PrimaryWide.TButton",
                                   command=self._on_book, state=tk.DISABLED)
        self.btn_book.pack(side=RIGHT)
        self.btn_multi_day = ttk.Button(primary_actions, text="选择日期并预约", style="PrimaryWide.TButton",
                                        command=self._start_multi_day, state=tk.DISABLED)
        self.btn_multi_day.pack_forget()
        self.seats_area.pack(fill=BOTH, expand=True)
        self.seats_area.set_seats([], self.config.show_only_available)

        # Bottom pane: compact, collapsible activity log
        bottom = ttk.Frame(split, height=150)
        bottom.pack_propagate(False)
        log_header = ttk.Frame(bottom)
        log_header.pack(fill=X, pady=(2, 5))
        ttk.Label(log_header, text="操作记录", style="Section.TLabel").pack(side=LEFT)
        ttk.Button(log_header, text="清空", command=self._clear_log).pack(side=RIGHT, padx=(4, 0))
        self.btn_toggle_log = ttk.Button(log_header, text="收起", command=self._toggle_log)
        self.btn_toggle_log.pack(side=RIGHT)
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
            self.btn_book.pack_forget()
            self.btn_multi_day.pack(side=RIGHT)
            self.date_label.config(text="预览日期")
            self.time_label.config(text="预览时段")
            self.date_label.grid()
            self.date_combo.grid()
            self.time_label.grid()
            self.time_button.grid()
            self.btn_multi_day.config(text="下一步：配置多天预约")
            self.selection_hint_var.set("第 1 步：按上方日期和时段预览，然后选择座位")
        else:
            self.btn_multi_day.pack_forget()
            self.date_label.config(text="日期")
            self.time_label.config(text="时段")
            self.date_label.grid()
            self.date_combo.grid()
            self.time_label.grid()
            self.time_button.grid()
            self.btn_book.pack(side=RIGHT)
            self.selection_hint_var.set("确认分区、日期和时段后提交")
        self._update_selection_summary()
        self._sync_book_button_state()

    # -- event handlers --

    def _selected_time_slots(self) -> List[dict]:
        selected = set(self._manual_time_labels)
        slots = [slot for slot in self.config.time_slots if slot.get("label") in selected]
        if not slots and self.config.time_slots:
            slots = [self.config.time_slots[0]]
            self._manual_time_labels = [slots[0]["label"]]
            self._sync_manual_time_summary()
        return slots

    def _sync_manual_time_summary(self) -> None:
        labels = list(self._manual_time_labels)
        if not labels:
            self.time_var.set("请选择时段")
        elif len(labels) == 1:
            self.time_var.set(labels[0])
        else:
            self.time_var.set(f"已选 {len(labels)} 个时段")

    def _selected_time_text(self) -> str:
        labels = list(self._manual_time_labels)
        if not labels:
            return "未选择时段"
        if len(labels) <= 2:
            return "、".join(labels)
        return f"{labels[0]} 等 {len(labels)} 个时段"

    def _set_manual_time_labels(self, labels: List[str], reload_seats: bool = True) -> None:
        valid = [slot["label"] for slot in self.config.time_slots]
        chosen = [label for label in valid if label in set(labels)]
        if not chosen and valid:
            chosen = [valid[0]]
        self._manual_time_labels = chosen
        self._sync_manual_time_summary()
        if chosen:
            for index, slot in enumerate(self.config.time_slots):
                if slot["label"] == chosen[0]:
                    self.config.set_auto_grab_time_slot_index(index)
                    break
        self._update_selection_summary()
        self._sync_book_button_state()
        if reload_seats and self.sub_floor_var.get():
            self._schedule_seat_reload()

    def _show_manual_time_picker(self) -> None:
        dlg = ttkb.Toplevel(title="选择时段")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        w, h = 420, 360
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_y() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(dlg, padding=(22, 18))
        frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text="选择一个或多个时段", style="Section.TLabel").pack(anchor=W)
        ttk.Label(
            frame,
            text="选择多个时段时，座位列表只显示这些时段都空闲的座位。",
            style="Meta.TLabel",
        ).pack(anchor=W, pady=(4, 14))

        vars_by_label: Dict[str, tk.BooleanVar] = {}
        selected = set(self._manual_time_labels)
        slots_frame = ttk.Frame(frame)
        slots_frame.pack(fill=BOTH, expand=True)
        for index, slot in enumerate(self.config.time_slots):
            label = slot["label"]
            var = tk.BooleanVar(value=label in selected)
            vars_by_label[label] = var
            ttk.Checkbutton(
                slots_frame,
                text=label,
                variable=var,
            ).grid(row=index // 2, column=index % 2, sticky=EW, pady=6, padx=4)
        slots_frame.columnconfigure(0, weight=1)
        slots_frame.columnconfigure(1, weight=1)

        def _select_all() -> None:
            for var in vars_by_label.values():
                var.set(True)

        def _clear() -> None:
            for var in vars_by_label.values():
                var.set(False)

        quick = ttk.Frame(frame)
        quick.pack(fill=X, pady=(8, 0))
        ttk.Button(quick, text="全选", command=_select_all).pack(side=LEFT)
        ttk.Button(quick, text="清空", command=_clear).pack(side=LEFT, padx=(8, 0))

        actions = ttk.Frame(frame)
        actions.pack(fill=X, pady=(18, 0))

        def _confirm() -> None:
            labels = [label for label, var in vars_by_label.items() if var.get()]
            if not labels:
                MB.show_info("请至少选择一个时段", "提示", parent=dlg)
                return
            dlg.destroy()
            self._set_manual_time_labels(labels)

        ttk.Button(actions, text="取消", command=dlg.destroy).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(actions, text="确定", command=_confirm, style="PrimaryWide.TButton").pack(side=RIGHT)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.bind("<Control-Return>", lambda _e: _confirm())

    def _on_time_change(self, *args: Any) -> None:
        if self.sub_floor_var.get():
            self._schedule_seat_reload()

    def _on_date_change(self, *args: Any) -> None:
        if self._refresh_after_id is not None:
            self.root.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.root.after(250, self._refresh_all)

    def _schedule_seat_reload(
        self,
        date_str: Optional[str] = None,
        begin: Optional[str] = None,
        end: Optional[str] = None,
    ) -> None:
        if self._seat_reload_after_id is not None:
            self.root.after_cancel(self._seat_reload_after_id)

        def _reload() -> None:
            self._seat_reload_after_id = None
            if date_str is not None and begin is not None and end is not None:
                self._load_seats_internal(self.sub_floor_var.get(), date_str, begin, end)
            else:
                self._load_seats()

        self._seat_reload_after_id = self.root.after(220, _reload)

    def _on_available_filter_change(self) -> None:
        show_only = self.show_available_var.get()
        self.config.set_show_only_available(show_only)
        self.seats_area.set_seats(self.seats, show_only)
        self._update_seat_count()
        self._update_selection_summary()
        self._sync_book_button_state()

    def _on_seat_selected(self, _event=None) -> None:
        self._update_selection_summary()
        self._sync_book_button_state()

    def _update_selection_summary(self) -> None:
        seat = self.seats_area.selected_seat
        if seat is None:
            if self.mode.get() == "multi":
                self.selection_var.set("第 1 步：选择一个可用座位")
                self.selection_hint_var.set("上方日期和时段仅用于预览该条件下的座位")
            else:
                self.selection_var.set("请选择一个可用座位")
                self.selection_hint_var.set("选中后即可提交当前日期与所选时段")
            return
        floor = self.sub_floor_var.get() or "当前分区"
        self.selection_var.set(f"已选择  {floor} · {seat.SEAT_NUM} 号座位")
        if self.mode.get() == "multi":
            self.selection_hint_var.set("第 1 步完成 · 点击右侧按钮配置日期与时段")
        else:
            self.selection_hint_var.set(f"{self.date_var.get()} · {self._selected_time_text()}")

    def _update_seat_count(self) -> None:
        total = len(self.seats)
        available = sum(1 for seat in self.seats if seat.is_available)
        if total:
            self.seat_count_var.set(f"可用 {available} / 共 {total}")
        else:
            self.seat_count_var.set("暂无座位数据")

    def _clear_log(self) -> None:
        self.log_panel.clear()
        self.log("操作记录已清空")

    def _toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log_panel.pack(fill=BOTH, expand=True)
            self.btn_toggle_log.config(text="收起")
        else:
            self.log_panel.pack_forget()
            self.btn_toggle_log.config(text="展开")

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
        dlg = ttkb.Toplevel(title="多天预约")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(True, True)
        dlg.minsize(600, 560)
        w, h = 680, 620
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_y() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        dates = self.config.get_available_dates()
        seat = self.seats_area.selected_seat
        seat_text = seat.SEAT_NUM if seat else "--"
        preview_date = self.date_var.get()
        start_index = dates.index(preview_date) if preview_date in dates else 0
        upcoming_dates = dates[start_index:]
        default_dates = set(upcoming_dates[:3])
        preview_slots = set(self._manual_time_labels)

        header = ttk.Frame(dlg, padding=(24, 20, 24, 12))
        header.pack(fill=X)
        ttk.Label(header, text="第 2 步：配置预约计划", style="Title.TLabel").pack(anchor=W)
        ttk.Label(
            header,
            text=f"目标座位  {sub_floor.get('FLOOR_NUM', '当前分区')} · {seat_text} 号",
            style="Selection.TLabel",
        ).pack(anchor=W, pady=(5, 2))
        ttk.Label(
            header,
            text="已默认选择从预览日期开始的 3 天，并沿用当前预览时段。",
            style="Meta.TLabel",
        ).pack(anchor=W)

        self._multi_vars: Dict[str, tk.BooleanVar] = {
            date: tk.BooleanVar(value=date in default_dates) for date in dates
        }
        slot_check_vars: List[tk.BooleanVar] = [
            tk.BooleanVar(value=slot["label"] in preview_slots)
            for slot in self.config.time_slots
        ]
        if slot_check_vars and not any(var.get() for var in slot_check_vars):
            slot_check_vars[0].set(True)

        summary_var = tk.StringVar()
        detail_var = tk.StringVar()
        submit_button: Optional[ttk.Button] = None

        def _current_selection() -> tuple[List[str], List[dict]]:
            selected_dates = [date for date in dates if self._multi_vars[date].get()]
            selected_slots = [
                self.config.time_slots[index]
                for index, var in enumerate(slot_check_vars)
                if var.get()
            ]
            return selected_dates, selected_slots

        def _update_summary() -> None:
            selected_dates, selected_slots = _current_selection()
            combinations = len(selected_dates) * len(selected_slots)
            summary_var.set(
                f"已选 {len(selected_dates)} 天 × {len(selected_slots)} 个时段 = {combinations} 次预约"
            )
            if not selected_dates:
                detail_var.set("请至少选择一个日期")
            elif not selected_slots:
                detail_var.set("请至少选择一个时段")
            else:
                detail_var.set("系统会按顺序提交，单次失败不会中断其余预约")
            if submit_button is not None:
                submit_button.config(
                    text=f"提交 {combinations} 次预约" if combinations else "请选择日期和时段",
                    state=tk.NORMAL if combinations else tk.DISABLED,
                )

        def _set_dates(selected: List[str]) -> None:
            selected_set = set(selected)
            for date, var in self._multi_vars.items():
                var.set(date in selected_set)
            _update_summary()

        quick = ttk.LabelFrame(dlg, text="快捷方案", padding=(12, 8), style="Card.TLabelframe")
        quick.pack(fill=X, padx=24, pady=(0, 12))
        for index in range(4):
            quick.columnconfigure(index, weight=1)
        ttk.Button(quick, text="连续 3 天", command=lambda: _set_dates(upcoming_dates[:3])).grid(
            row=0, column=0, sticky=EW, padx=3
        )
        ttk.Button(quick, text="连续 7 天", command=lambda: _set_dates(upcoming_dates[:7])).grid(
            row=0, column=1, sticky=EW, padx=3
        )
        ttk.Button(
            quick,
            text="全部工作日",
            command=lambda: _set_dates(
                [
                    date for date in upcoming_dates
                    if datetime.strptime(date, "%Y-%m-%d").weekday() < 5
                ]
            ),
        ).grid(row=0, column=2, sticky=EW, padx=3)
        ttk.Button(quick, text="清空", command=lambda: _set_dates([])).grid(
            row=0, column=3, sticky=EW, padx=3
        )

        selectors = ttk.Frame(dlg)
        selectors.pack(fill=BOTH, expand=True, padx=24)
        selectors.columnconfigure(0, weight=2, minsize=210)
        selectors.columnconfigure(1, weight=3, minsize=330)
        selectors.rowconfigure(0, weight=1)

        date_panel = ttk.LabelFrame(
            selectors, text="1. 选择日期", padding=(10, 8), style="Card.TLabelframe"
        )
        date_panel.grid(row=0, column=0, sticky=NSEW, padx=(0, 6))
        time_panel = ttk.LabelFrame(
            selectors, text="2. 选择时段", padding=(10, 8), style="Card.TLabelframe"
        )
        time_panel.grid(row=0, column=1, sticky=NSEW, padx=(6, 0))

        canvas = tk.Canvas(
            date_panel, highlightthickness=0, borderwidth=0,
            background=PALETTE["background"],
        )
        vsb = ttk.Scrollbar(date_panel, orient=VERTICAL, command=canvas.yview)
        date_list = ttk.Frame(canvas)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        win_id = canvas.create_window((0, 0), window=date_list, anchor="nw")
        date_list.bind(
            "<Configure>", lambda _e: canvas.config(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfig(win_id, width=max(1, e.width))
        )

        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for index, date in enumerate(dates):
            weekday = weekday_names[datetime.strptime(date, "%Y-%m-%d").weekday()]
            relative = "今天" if index == 0 else "明天" if index == 1 else weekday
            ttk.Checkbutton(
                date_list,
                text=f"{date}   {relative}",
                variable=self._multi_vars[date],
                command=_update_summary,
            ).pack(anchor=W, fill=X, pady=4, padx=4)

        time_panel.columnconfigure(0, weight=1)
        time_panel.columnconfigure(1, weight=1)
        for index, slot in enumerate(self.config.time_slots):
            ttk.Checkbutton(
                time_panel,
                text=slot["label"],
                variable=slot_check_vars[index],
                command=_update_summary,
            ).grid(
                row=index // 2, column=index % 2,
                sticky=EW, pady=6, padx=4,
            )

        def _on_mw(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mw))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        dlg.bind(
            "<Destroy>",
            lambda event: canvas.unbind_all("<MouseWheel>") if event.widget == dlg else None,
        )

        footer = ttk.Frame(dlg, padding=(24, 14, 24, 18))
        footer.pack(fill=X, side=BOTTOM, before=selectors)
        footer_actions = ttk.Frame(footer)
        footer_actions.pack(side=RIGHT, padx=(16, 0))
        summary_box = ttk.Frame(footer)
        summary_box.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(summary_box, textvariable=summary_var, style="Selection.TLabel").pack(anchor=W)
        ttk.Label(summary_box, textvariable=detail_var, style="Meta.TLabel").pack(
            anchor=W, pady=(2, 0)
        )

        def _confirm() -> None:
            selected, chosen_slots = _current_selection()
            combinations = len(selected) * len(chosen_slots)
            if not combinations:
                return
            if combinations > 10 and not MB.okcancel(
                f"即将连续提交 {combinations} 次预约，是否继续？", "确认批量预约", parent=dlg
            ):
                return
            self._multi_dates = selected
            self._multi_slots = chosen_slots
            dlg.destroy()
            self.log(
                f"多天预约：{len(selected)} 天 × {len(chosen_slots)} 时段，共 {combinations} 次"
            )
            self._sync_book_button_state()
            self._run_multi_day_booking(sub_floor)

        def _cancel() -> None:
            self._multi_dates = []
            dlg.destroy()
            self._sync_book_button_state()

        dlg.protocol("WM_DELETE_WINDOW", _cancel)
        dlg.bind("<Escape>", lambda _e: _cancel())
        ttk.Button(footer_actions, text="取消", command=_cancel).pack(side=RIGHT, padx=(8, 0))
        submit_button = ttk.Button(
            footer_actions, text="提交预约", command=_confirm, style="PrimaryWide.TButton"
        )
        submit_button.pack(side=RIGHT)
        _update_summary()

    def _on_sub_floor_change(self, *args: Any) -> None:
        text = self.sub_floor_var.get()
        for sf in self.sub_floors:
            if sf.get("FLOOR_NUM") == text:
                self.selected_sub_floor = sf
                break
        self._schedule_seat_reload()
        self._update_selection_summary()
        self._sync_book_button_state()

    # -- refresh (floors + sub-floors) --

    def _refresh_all(self) -> None:
        self._refresh_after_id = None
        # Any in-flight seat response belongs to the previous selection.
        self._seat_request_id += 1
        # If cookie not loaded yet, trigger Playwright login
        if not self.api._cookie_loaded:
            self.log("未登录，启动浏览器...")
            self._open_browser_login()
            return
        if self._refreshing:
            return
        self._set_refreshing(True)
        self.seats = []
        self.seats_area.set_seats(
            [], self.config.show_only_available, empty_message="正在刷新场所与分区…"
        )
        self.seat_count_var.set("正在刷新…")
        self._update_selection_summary()
        self.log("正在刷新...")
        self.status_bar.set_step("刷新中...")
        self.threaded_api.async_get_floors()

    def _set_refreshing(self, refreshing: bool) -> None:
        self._refreshing = refreshing
        self.btn_refresh.config(
            state=tk.DISABLED if refreshing else tk.NORMAL,
            text="刷新中…" if refreshing else "刷新  F5",
        )
        if refreshing:
            self.btn_book.config(state=tk.DISABLED)
            self.btn_multi_day.config(state=tk.DISABLED)
        else:
            self._sync_book_button_state()

    def _load_seats(self) -> None:
        sub_floor_text = self.sub_floor_var.get()
        date_str = self.date_var.get()

        if not sub_floor_text or not date_str:
            return

        slots = self._selected_time_slots()
        if len(slots) == 1:
            self._load_seats_internal(
                sub_floor_text, date_str, slots[0]["begin"], slots[0]["end"]
            )
            return
        self._load_seats_for_slots(sub_floor_text, date_str, slots)

    def _load_seats_internal(self, sub_floor_text: str, date_str: str, begin: str, end: str) -> None:
        self._load_seats_for_slots(
            sub_floor_text,
            date_str,
            [{"label": f"{begin}-{end}", "begin": begin, "end": end}],
            force_single_request=True,
        )

    def _load_seats_for_slots(
        self,
        sub_floor_text: str,
        date_str: str,
        slots: List[dict],
        force_single_request: bool = False,
    ) -> None:
        place_wid = ""
        for sf in self.sub_floors:
            if sf.get("FLOOR_NUM") == sub_floor_text:
                place_wid = sf.get("PLACE_WID", "")
                self.selected_sub_floor = sf
                break
        if not place_wid:
            self.log("未找到分区信息，请刷新")
            return

        slot_count = len(slots)
        if slot_count > 1:
            self.log(f"正在获取 {sub_floor_text} 多时段共同空闲座位 ({slot_count} 个时段)...")
        else:
            self.log(f"正在获取 {sub_floor_text} 座位...")
        self.status_bar.set_step("获取座位中...")
        self.seat_count_var.set("正在加载座位…")
        self.seats = []
        self.seats_area.set_seats(
            [], self.config.show_only_available, empty_message="正在加载座位…"
        )
        self._update_selection_summary()
        self.btn_book.config(state=tk.DISABLED)
        self.btn_multi_day.config(state=tk.DISABLED)
        self._seat_request_id += 1
        request_id = self._seat_request_id
        if force_single_request or len(slots) == 1:
            slot = slots[0]
            self.threaded_api.async_get_seats(
                place_wid,
                sub_floor_text,
                date_str,
                slot["begin"],
                slot["end"],
                request_id,
            )
            return

        def _worker() -> None:
            available_by_wid: Optional[Dict[str, SeatInfo]] = None
            try:
                for index, slot in enumerate(slots, start=1):
                    ok, data = self.api.get_seats(
                        place_wid,
                        sub_floor_text,
                        date_str,
                        slot["begin"],
                        slot["end"],
                    )
                    if ok == "expired":
                        self.queue.put(("result", (("seats", request_id), ("expired", data))))
                        return
                    if not ok:
                        self.queue.put(("result", (("seats", request_id), (False, data))))
                        return
                    if not isinstance(data, list):
                        self.queue.put(("result", (("seats", request_id), (False, "座位响应格式错误"))))
                        return
                    slot_available = {
                        seat.WID: seat
                        for seat in data
                        if isinstance(seat, SeatInfo) and seat.WID and seat.is_available
                    }
                    if available_by_wid is None:
                        available_by_wid = slot_available
                    else:
                        available_by_wid = {
                            wid: seat
                            for wid, seat in available_by_wid.items()
                            if wid in slot_available
                        }
                    self.queue.put((
                        "result",
                        f"已匹配 {index}/{slot_count} 个时段，共同空闲 {len(available_by_wid or {})} 个座位",
                    ))
                    if not available_by_wid:
                        break
                seats = sorted(
                    list((available_by_wid or {}).values()),
                    key=lambda seat: [
                        part.zfill(8) if part.isdigit() else part
                        for part in re.split(r"(\d+)", seat.SEAT_NUM)
                    ],
                )
                self.queue.put(("result", (("seats", request_id), (True, seats))))
            except Exception as exc:
                self.queue.put(("result", (("seats", request_id), (False, str(exc)))))

        threading.Thread(target=_worker, daemon=True).start()

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
                self._set_refreshing(False)
                self._unlock_controls()
            elif item_type == "auth_expired":
                self.log("Cookie 已过期，请重新登录")
                self._set_refreshing(False)
                self._open_browser_login()
            elif item_type == "login_finished":
                self._login_in_progress = False
            elif item_type == "refresh_seats":
                self.root.after(350, self._schedule_seat_reload)
            elif item_type == "booking_finished":
                self._booking_finished()
            elif item_type == "multi_next":
                seat, sub_floor = data
                self._process_next_multi(seat, sub_floor)
            elif item_type == "single_slot_next":
                seat, sub_floor = data
                self._process_next_single_slot(seat, sub_floor)
        self.root.after(200, self._process_queue)

    def _handle_result(self, result: Any) -> None:
        if isinstance(result, str):
            self.log(result)
            if "预约成功" in result or result.startswith("成功"):
                self.status_bar.set_step("预约成功")
            elif any(word in result for word in ("预约失败", "预约异常", "失败 ", "异常 ")):
                self.status_bar.set_step("预约未完成")
            return

        result_tags = {"floors", "sub_floors", "seats", "violations", "records", "cancel"}
        tag = ""
        request_id = None
        if isinstance(result, tuple) and len(result) == 2:
            raw_tag = result[0]
            if isinstance(raw_tag, tuple) and len(raw_tag) == 2 and raw_tag[0] in result_tags:
                tag, request_id = raw_tag
                result = result[1]
            elif raw_tag in result_tags:
                tag, result = result

        if tag == "seats" and request_id != self._seat_request_id:
            log.info("discarded stale seat response %s (current=%s)", request_id, self._seat_request_id)
            return

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
                    self.seats_area.set_seats(
                        [], self.config.show_only_available,
                        empty_message="座位加载失败，请刷新后重试",
                    )
                    reason = data if isinstance(data, str) else "未知错误"
                    self.log(f"加载座位失败: {reason}")
                    self.status_bar.set_step("加载失败")
                    self._update_seat_count()
                    self._update_selection_summary()
                    self._sync_book_button_state()
                    return
                if isinstance(data, list):
                    self.seats = data
                    avail = sum(1 for s in data if s.is_available)
                    self.seats_area.set_seats(data, self.config.show_only_available)
                    self.log(f"获取到 {len(data)} 个座位 (可用: {avail})")
                    self.status_bar.set_step("请选择座位" if data else "无座位")
                    self._update_seat_count()
                    self._update_selection_summary()
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
                    if hasattr(self, "_records_set_idle"):
                        self._records_set_idle()
                elif ok and isinstance(data, dict):
                    total = data.get("total", 0)
                    self.log(f"查询到 {total} 条预约记录")
                    if hasattr(self, '_records_update'):
                        self._records_update(data)
                else:
                    reason = data.get("error", "未知错误") if isinstance(data, dict) else str(data)
                    self.log(f"查询预约记录失败: {reason}")
                    if hasattr(self, "_records_set_idle"):
                        self._records_set_idle()
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
                self._set_refreshing(False)
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self.seats_area.set_seats(
                        [], self.config.show_only_available, empty_message="登录后显示座位"
                    )
                    self.seat_count_var.set("登录已过期")
                    self._open_browser_login()
                else:
                    self.floors = []
                    reason = data if isinstance(data, str) else ("无数据" if not ok else "响应为空")
                    self.log(f"加载场所失败: {reason}")
                    self.seats_area.set_seats(
                        [], self.config.show_only_available, empty_message="场所加载失败，请按 F5 重试"
                    )
                    self.seat_count_var.set("场所加载失败")
                self._sync_book_button_state()
                return

            if tag == "sub_floors" and (ok == "expired" or not ok or not data):
                self._set_refreshing(False)
                if ok == "expired":
                    self.log("Cookie 已过期，请重新登录")
                    self.seats_area.set_seats(
                        [], self.config.show_only_available, empty_message="登录后显示座位"
                    )
                    self.seat_count_var.set("登录已过期")
                    self._open_browser_login()
                else:
                    self.sub_floors = []
                    self.sub_floor_combo["values"] = []
                    reason = data if isinstance(data, str) else ("无数据" if not ok else "响应为空")
                    self.log(f"加载分区失败: {reason}")
                    self.status_bar.set_step("加载失败" if not ok else "无分区")
                    self.seats_area.set_seats(
                        [], self.config.show_only_available, empty_message="暂无可用分区"
                    )
                    self.seat_count_var.set("暂无分区")
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
                self._set_refreshing(False)
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
                self._update_seat_count()
                self._update_selection_summary()
                self._sync_book_button_state()
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
        if self.booking_in_progress or self._refreshing:
            self.btn_book.config(state=tk.DISABLED)
            self.btn_multi_day.config(state=tk.DISABLED)
            return
        if self.mode.get() == "multi":
            ready = bool(self.sub_floor_var.get() and self.seats_area.selected_seat)
            self.btn_multi_day.config(state=tk.NORMAL if ready else tk.DISABLED)
        else:
            ready = bool(self.sub_floor_var.get() and self.date_var.get()
                         and self._selected_time_slots() and self.seats_area.selected_seat)
            self.btn_book.config(state=tk.NORMAL if ready else tk.DISABLED)

    # -- booking flow (manual) --

    def _on_book(self) -> None:
        error = self._validate_booking_ready()
        if error:
            MB.show_error("无法预约", error)
            self.log(f"预约校验未通过: {error}")
            return
        if self.mode.get() == "multi":
            self._start_multi_day()
        else:
            self._submit_manual_booking()

    def _submit_manual_booking(self) -> None:
        error = self._validate_booking_ready()
        if error:
            MB.show_error("无法预约", error)
            self.log(f"预约校验未通过: {error}")
            return
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

        slots = self._selected_time_slots()
        if not slots:
            MB.show_error("提示", "请至少选择一个时段")
            return
        if len(slots) > 1:
            self._run_single_day_slot_booking(
                seat=seat,
                sub_floor=sub_floor,
                date_str=self.date_var.get(),
                slots=slots,
            )
            return
        begin, end = slots[0]["begin"], slots[0]["end"]
        self._run_booking_flow(seat=seat, sub_floor=sub_floor,
                               date_str=self.date_var.get(), begin=begin, end=end)

    def _run_single_day_slot_booking(
        self,
        seat: SeatInfo,
        sub_floor: dict,
        date_str: str,
        slots: List[dict],
    ) -> None:
        self._single_slot_pending = [(date_str, slot["begin"], slot["end"]) for slot in slots]
        self._single_slot_success = 0
        self._single_slot_fail = 0
        self._single_slot_total = len(self._single_slot_pending)
        self.booking_in_progress = True
        self.btn_book.config(state=tk.DISABLED)
        self.btn_multi_day.config(state=tk.DISABLED)
        self.status_bar.set_step(f"单日预约 0/{self._single_slot_total}...")
        self.log("=" * 40)
        self.log(f"单日多时段预约: {sub_floor.get('FLOOR_NUM')} {seat.SEAT_NUM} {date_str}")
        self.log(f"时段: {', '.join(slot['label'] for slot in slots)}")
        self._process_next_single_slot(seat, sub_floor)

    def _process_next_single_slot(self, seat: SeatInfo, sub_floor: dict) -> None:
        if not self._single_slot_pending:
            self._booking_finished()
            self.log(
                f"单日多时段预约完成: 成功 {self._single_slot_success}, 失败 {self._single_slot_fail}"
            )
            self.status_bar.set_step(
                f"批量完成 · 成功 {self._single_slot_success} / 失败 {self._single_slot_fail}"
            )
            self.queue.put(("refresh_seats", None))
            return
        date_str, begin, end = self._single_slot_pending.pop(0)
        done = self._single_slot_total - len(self._single_slot_pending)
        self.status_bar.set_step(f"单日预约 {done}/{self._single_slot_total} — {begin}-{end}")

        def _flow() -> None:
            try:
                api = self.api
                if done == 1:
                    api.read_notice()
                    banned, ban_msg = is_banned(api.get_user_id())
                    if banned:
                        self._single_slot_pending.clear()
                        self._single_slot_fail += 1
                        self.queue.put(("result", f"预约失败: {ban_msg}"))
                        return
                ok, msg = api.submit_booking(
                    seat,
                    sub_floor["PLACE_WID"],
                    sub_floor["WID"],
                    sub_floor.get("FLOOR_NUM", ""),
                    date_str,
                    begin,
                    end,
                )
                if ok == "expired":
                    self._single_slot_pending.clear()
                    self._single_slot_fail += 1
                    self.queue.put(("auth_expired", msg))
                    return
                if ok:
                    self._single_slot_success += 1
                    self.queue.put(("result", f"成功 {date_str} {begin}-{end} {msg}"))
                    report_booking(api, sub_floor, seat, date_str, begin, end)
                else:
                    self._single_slot_fail += 1
                    self.queue.put(("result", f"失败 {date_str} {begin}-{end} {msg or '未知错误'}"))
            except Exception as exc:
                self._single_slot_fail += 1
                self.queue.put(("result", f"异常 {date_str} {begin}-{end} {exc}"))
            finally:
                self.queue.put(("single_slot_next", (seat, sub_floor)))

        threading.Thread(target=_flow, daemon=True).start()

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
            self.status_bar.set_step(
                f"批量完成 · 成功 {self._multi_success} / 失败 {self._multi_fail}"
            )
            return
        date_str, begin, end = self._multi_pending.pop(0)
        done = self._multi_total - len(self._multi_pending)
        self.status_bar.set_step(f"多天预约 {done}/{self._multi_total} — {date_str} {begin}-{end}")

        def _flow() -> None:
            try:
                api = self.api
                api.read_notice()
                banned, ban_msg = is_banned(api.get_user_id())
                if banned:
                    self._multi_fail += 1
                    self.queue.put(("result", f"失败 {date_str} {begin}-{end} {ban_msg}"))
                    return
                ok, msg = api.submit_booking(seat, sub_floor["PLACE_WID"], sub_floor["WID"],
                                             sub_floor.get("FLOOR_NUM", ""), date_str, begin, end)
                if ok == "expired":
                    self._multi_pending.clear()
                    self._multi_fail += 1
                    self.queue.put(("auth_expired", msg))
                    return
                if ok:
                    self._multi_success += 1
                    self.queue.put(("result", f"成功 {date_str} {begin}-{end} {msg}"))
                    report_booking(api, sub_floor, seat, date_str, begin, end)
                else:
                    self._multi_fail += 1
                    self.queue.put(("result", f"失败 {date_str} {begin}-{end} {msg or '未知错误'}"))
            except Exception as exc:
                self._multi_fail += 1
                self.queue.put(("result", f"异常 {date_str} {begin}-{end} {exc}"))
            finally:
                self.queue.put(("multi_next", (seat, sub_floor)))
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
                banned, ban_msg = is_banned(api.get_user_id())
                if banned:
                    self.queue.put(("result", f"预约失败: {ban_msg}"))
                    return
                ok, msg = api.submit_booking(seat, sub_floor["PLACE_WID"], sub_floor["WID"],
                                             sub_floor.get("FLOOR_NUM", ""), date_str, begin, end)
                if ok == "expired":
                    self.queue.put(("auth_expired", msg))
                    return
                if ok:
                    self.queue.put(("result", f"预约成功: {seat.SEAT_NUM} {date_str} {begin}-{end}"))
                    self.queue.put(("refresh_seats", None))
                    report_booking(api, sub_floor, seat, date_str, begin, end)
                else:
                    self.queue.put(("result", f"预约失败: {msg or '未知错误'}"))
            except Exception as exc:
                self.queue.put(("result", f"预约异常: {exc}"))
            finally:
                self.queue.put(("booking_finished", None))

        threading.Thread(target=_flow, daemon=True).start()

    def _booking_finished(self) -> None:
        self.booking_in_progress = False
        self._unlock_controls()

    @property
    def selected_seat(self) -> Optional[SeatInfo]:
        return self.seats_area.selected_seat

    # -- appointment records --

    def _show_records(self) -> None:
        if hasattr(self, "_records_dialog") and self._records_dialog.winfo_exists():
            self._records_dialog.lift()
            self._records_dialog.focus_force()
            return
        dlg = ttkb.Toplevel(title="预约记录")
        self._records_dialog = dlg
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
        query_button: Optional[ttk.Button] = None

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
            if query_button is not None:
                query_button.config(state=tk.DISABLED, text="查询中…")
            self.threaded_api.async_get_appointment_records(d, 1, page_size, _get_filter_value())
            self.log(f"正在查询 {d} 的预约记录...")

        query_button = ttk.Button(top_bar, text="查询", command=_load_records)
        query_button.pack(side=LEFT, padx=8)

        # --- treeview ---
        cols = ("floor", "seat", "begin", "end", "cancelled", "violated", "created")
        tree_frame = ttk.Frame(dlg, padding=(10, 0, 10, 0))
        tree_frame.pack(fill=BOTH, expand=True)
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14,
                            selectmode="extended")
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
        previous_button: Optional[ttk.Button] = None
        next_button: Optional[ttk.Button] = None

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
            total_pages = max(1, (total + page_size - 1) // page_size)
            if previous_button is not None:
                previous_button.config(state=tk.NORMAL if page > 1 else tk.DISABLED)
            if next_button is not None:
                next_button.config(state=tk.NORMAL if page < total_pages else tk.DISABLED)
            if query_button is not None:
                query_button.config(state=tk.NORMAL, text="查询")
            for index, r in enumerate(rows):
                begin_short = r.BEGINNING_DATE[5:16] if len(r.BEGINNING_DATE) > 10 else r.BEGINNING_DATE
                end_short = r.ENDING_DATE[5:16] if len(r.ENDING_DATE) > 10 else r.ENDING_DATE
                created_short = r.CREATED_AT[5:16] if len(r.CREATED_AT) > 10 else r.CREATED_AT
                iid = tree.insert("", tk.END, values=(
                    r.FLOOR_DISPLAY, r.SEAT_DISPLAY,
                    begin_short, end_short,
                    r.IS_CANCELLED, r.IS_VIOLATED, created_short
                ), tags=("even" if index % 2 == 0 else "odd",))
                record_data[iid] = {
                    "wid": r.WID,
                    "ending_date": r.ENDING_DATE,
                    "beginning_date": r.BEGINNING_DATE,
                    "seat": r.SEAT_DISPLAY,
                    "is_cancelled": r.IS_CANCELLED,
                }

        def _set_records_idle() -> None:
            if query_button is not None and query_button.winfo_exists():
                query_button.config(state=tk.NORMAL, text="查询")

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
                MB.show_warning("请先选择要取消的预约记录（按住 Ctrl 可多选）", "提示")
                return
            records = []
            for iid in sel:
                info = record_data.get(iid, {})
                if info.get("is_cancelled") == "是":
                    continue
                wid = info.get("wid", "")
                if not wid:
                    continue
                records.append({
                    "wid": wid,
                    "ending_date": info.get("ending_date", ""),
                    "beginning_date": info.get("beginning_date", ""),
                    "seat": info.get("seat", ""),
                })
            if not records:
                MB.show_info("所选记录均已取消", "提示")
                return
            if len(records) == 1:
                msg = "确定要取消这条预约吗？"
            else:
                msg = f"确定要取消选中的 {len(records)} 条预约吗？"
            if not MB.okcancel(msg, "确认取消"):
                return
            self.threaded_api.async_cancel_appointments(records)
            self._records_refresh = _load_records
            self.log(f"正在取消 {len(records)} 条预约...")

        cancel_button = ttk.Button(bot_bar, text="取消预约", style="Danger.TButton",
                                   command=_cancel_selected, state=tk.DISABLED)
        cancel_button.pack(side=LEFT, padx=(20, 4))
        hint = ttk.Label(bot_bar, text="提示：按住 Ctrl 可多选，支持批量取消",
                         style="Meta.TLabel")
        hint.pack(side=LEFT, padx=4)
        next_button = ttk.Button(bot_bar, text="下一页", command=_next_page, state=tk.DISABLED)
        next_button.pack(side=RIGHT, padx=4)
        previous_button = ttk.Button(bot_bar, text="上一页", command=_prev_page, state=tk.DISABLED)
        previous_button.pack(side=RIGHT, padx=4)
        tree.tag_configure("even")
        tree.tag_configure("odd")
        tree.bind(
            "<<TreeviewSelect>>",
            lambda _e: cancel_button.config(state=tk.NORMAL if tree.selection() else tk.DISABLED),
        )
        filter_combo.bind("<<ComboboxSelected>>", lambda _e: _load_records())
        date_combo.bind("<<ComboboxSelected>>", lambda _e: _load_records())

        # Store references for queue handler
        self._records_tree = tree
        self._records_update = _update_tree
        self._records_refresh = _load_records
        self._records_set_idle = _set_records_idle

        def _close_records() -> None:
            for name in ("_records_dialog", "_records_tree", "_records_update",
                         "_records_refresh", "_records_set_idle"):
                if hasattr(self, name):
                    delattr(self, name)
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", _close_records)
        dlg.bind("<Escape>", lambda _e: _close_records())

        # Load initial data
        _load_records()

    # -- settings --

    def _show_settings(self) -> None:
        dlg = ttkb.Toplevel(title="设置")
        dlg.resizable(False, False)
        w, h = 520, 280
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_y() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.transient(self.root)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=(24, 20))
        frm.pack(fill=BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="偏好设置", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=W, pady=(0, 4)
        )
        ttk.Label(frm, text="调整预约范围与默认座位显示方式",
                  style="Meta.TLabel").grid(row=1, column=0, columnspan=2, sticky=W, pady=(0, 18))

        ttk.Label(frm, text="可预约日期范围").grid(row=2, column=0, sticky=W, pady=7)
        days_var = tk.IntVar(value=self.config.date_range_days)
        days_frame = ttk.Frame(frm)
        days_frame.grid(row=2, column=1, sticky=EW, pady=7)
        ttk.Spinbox(days_frame, from_=1, to=30, textvariable=days_var,
                    width=8).pack(side=LEFT)
        ttk.Label(days_frame, text="天", style="Meta.TLabel").pack(side=LEFT, padx=(6, 0))

        avail_var = tk.BooleanVar(value=self.config.show_only_available)
        ttk.Checkbutton(frm, text="默认仅显示可用座位", variable=avail_var).grid(
            row=3, column=0, columnspan=2, pady=(10, 6), sticky=W
        )

        action_bar = ttk.Frame(frm)
        action_bar.grid(row=4, column=0, columnspan=2, sticky=EW, pady=(18, 0))

        def _save() -> None:
            self.config.set_date_range_days(days_var.get())
            self.config.set_show_only_available(avail_var.get())
            self.show_available_var.set(avail_var.get())
            self.seats_area.set_seats(self.seats, avail_var.get())
            self._update_seat_count()
            self._update_selection_summary()
            self._sync_book_button_state()
            new_dates = self.config.get_available_dates()
            self.date_combo["values"] = new_dates
            if new_dates:
                self.date_var.set(new_dates[0])
            dlg.destroy()
            self.log("设置已保存")
            self.status_bar.set_step("设置已更新")

        ttk.Button(action_bar, text="取消", command=dlg.destroy).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(action_bar, text="保存设置", command=_save,
                   style="PrimaryWide.TButton").pack(side=RIGHT)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.bind("<Control-Return>", lambda _e: _save())

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.api.close()
