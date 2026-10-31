"""Background execution adapter for the synchronous appointment API."""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Optional

from .api_client import APIClient


class ThreadedAPIClient:
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
                  result_tag: Optional[Any] = None, **kwargs: Any) -> None:
        def worker() -> None:
            try:
                result = fn(*args, **kwargs)
                if result_tag is not None:
                    self._queue.put(("result", (result_tag, result)))
                else:
                    self._queue.put(("result", result))
            except Exception as exc:
                self._queue.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def async_get_floors(self) -> None:
        self._dispatch(self._client.get_floors, result_tag="floors")

    def async_get_seats(self, place_wid: str, floor_num: str,
                        date_str: str, begin: str, end: str, request_id: int) -> None:
        self._dispatch(
            self._client.get_seats,
            place_wid,
            floor_num,
            date_str,
            begin,
            end,
            result_tag=("seats", request_id),
        )

    def async_check_violations(self) -> None:
        self._dispatch(self._client.get_violations, result_tag="violations")

    def async_get_sub_floors(self, place_wid: str, date_str: str) -> None:
        self._dispatch(self._client.get_sub_floors, place_wid, date_str, result_tag="sub_floors")

    def async_get_appointment_records(self, date_str: str, page: int = 1,
                                      page_size: int = 10, cancelled_filter: str = "") -> None:
        self._dispatch(
            self._client.get_appointment_records,
            date_str,
            page,
            page_size,
            cancelled_filter,
            result_tag="records",
        )

    def async_cancel_appointment(self, wid: str, ending_date: str) -> None:
        record = {"wid": wid, "ending_date": ending_date}
        self._dispatch(self._client.cancel_appointment, wid, ending_date, result_tag=("cancel", [record]))

    def async_cancel_appointments(self, records: list[dict]) -> None:
        self._dispatch(self._client.cancel_appointments, records, result_tag=("cancel", records))
