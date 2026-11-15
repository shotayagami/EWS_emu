"""Synthetic service-ID examples for GUI and descriptor demonstrations only."""

from area_codes import AREAS

DEMO_AREA_GROUPS = {name: group for group, (name, _code) in enumerate(AREAS, 1)}
DEMO_AREA_GROUPS["地域共通"] = None
DEMO_SERVICES = tuple(
    (group, 0xF000 + (group - 1) * 2 + slot, f"ダミー局{group:02d}-{slot + 1}")
    for group in range(1, len(AREAS) + 1)
    for slot in range(2)
)
