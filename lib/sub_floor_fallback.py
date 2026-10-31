"""Minimal last-known partition map used only when the live API is unavailable."""

from __future__ import annotations


_PLACE_WID = "fb9dedd807fc48a59dc19338a50ea099"
_ROWS = (
    ("39bd32fd4f3d417f9c787351200b3cd0", "三层-西区-C区"),
    ("d19b1a281d1e447d9d118de58c4c6628", "二层-西区-A区"),
    ("9eede20e61ea4c4a85ae31dd3035fc6b", "二层-西区-D区"),
    ("bf36f271125547538bbc0e02bdbbc9e5", "二层-北区"),
    ("43ba1a9883ac409c947f7107520b7ae2", "二层-东区-A区"),
    ("0558e4243c8e4eeb84ed1d8f655a0b98", "二层-东区-B区"),
    ("227056D931865113E06301120A0A7414", "三层-西区-A区"),
    ("227056D931885113E06301120A0A7414", "三层-西区-D区"),
    ("227056D931895113E06301120A0A7414", "三层-北区"),
    ("227056D9318A5113E06301120A0A7414", "三层-东区-A区"),
    ("227056D9318B5113E06301120A0A7414", "三层-东区-B区"),
    ("227056D9318D5113E06301120A0A7414", "三层-东区-C区"),
    ("227056D9318E5113E06301120A0A7414", "三层-东区-D区"),
    ("befaea6c56c9461ea03aa35ccaff625a", "三层-西区-B区"),
    ("3a3612595f1c46cab72753ef42f0a7a7", "二层-西区-B区"),
    ("df4ae4ea97584ae3b12994ae539e22a6", "二层-东区-C区"),
    ("0ef331778f1a4b8d873b6bc9effc33d7", "二层-东区-D区"),
    ("1bb4a4c88dca4111bfa3310961112705", "二层-西区-C区"),
)


def get_fallback_sub_floors(place_wid: str) -> list[dict[str, str]]:
    if place_wid and place_wid != _PLACE_WID:
        return []
    return [
        {"PLACE_WID": _PLACE_WID, "WID": wid, "FLOOR_NUM": name}
        for wid, name in _ROWS
    ]
