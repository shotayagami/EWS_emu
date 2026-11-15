"""Digital broadcast emergency information descriptor serialization."""

import os
import tempfile
from pathlib import Path


def build_emergency_descriptor(service_id: int, started: bool, second_kind: bool, area: str) -> bytes:
    if not 0 <= service_id <= 0xFFFF:
        raise ValueError("service_idは0〜65535で指定してください")
    if len(area) != 12 or any(bit not in "01" for bit in area):
        raise ValueError("地域符号は0と1の12桁で指定してください")

    # One service loop and one area code. Reserved bits are set to 1.
    payload = (
        service_id.to_bytes(2, "big")
        + bytes(((int(started) << 7) | (int(second_kind) << 6) | 0x3F, 2))
        + ((int(area, 2) << 4) | 0x0F).to_bytes(2, "big")
    )
    return bytes((0xFC, len(payload))) + payload


def write_descriptor(path: Path, descriptor: bytes) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temporary:
            temporary_path = temporary.name
            temporary.write(descriptor)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
