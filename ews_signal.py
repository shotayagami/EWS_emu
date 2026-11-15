"""EWS audio FSK signal construction and PCM WAV output."""

from __future__ import annotations

import math
import os
import tempfile
import wave
from array import array
from datetime import datetime, timedelta
from pathlib import Path

BIT_RATE = 64
SAMPLE_RATE = 48_000
SAMPLES_PER_BIT = SAMPLE_RATE // BIT_RATE
FIRST_FIXED = "0000111001101101"
SECOND_FIXED = "1111000110010010"
AREA_COMMON = "001101001101"
MAX_BLOCKS = 100


def _lsb(value: int, width: int) -> str:
    return "".join(str((value >> bit) & 1) for bit in range(width))


def _date_time_code(when: datetime, sent_at: datetime, block_number: int) -> tuple[str, str]:
    date_for_code = when
    time_for_code = when
    day_mark = hour_mark = "0"
    if block_number % 2 == 0:
        if sent_at.hour == 0 and sent_at.minute < 10:
            date_for_code -= timedelta(days=1)
            day_mark = "1"
        elif sent_at.hour == 23 and sent_at.minute >= 50:
            date_for_code += timedelta(days=1)
            day_mark = "1"
        if sent_at.minute < 10:
            time_for_code -= timedelta(hours=1)
            hour_mark = "1"
        elif sent_at.minute >= 50:
            time_for_code += timedelta(hours=1)
            hour_mark = "1"

    month_code = _lsb(date_for_code.month, 4) + "1"
    day_code = _lsb(date_for_code.day, 5)
    hour_value = time_for_code.hour % 8 + 8 * (3 - time_for_code.hour // 8)
    hour_code = _lsb(hour_value, 5)
    year_digit = date_for_code.year % 10 or 10
    year_code = _lsb(year_digit + 16, 5)
    date_field = "010" + day_code + day_mark + month_code + "00"
    time_field = "011" + hour_code + hour_mark + year_code + "00"
    return date_field, time_field


def build_block(kind: str, signal_type: str, area: str, when: datetime, block_number: int) -> str:
    if kind not in {"start", "end"} or signal_type not in {"first", "second"}:
        raise ValueError("信号の種類が不正です")
    if len(area) != 12 or any(bit not in "01" for bit in area):
        raise ValueError("地域符号は0と1の12桁で指定してください")

    date_field, time_field = _date_time_code(when, when, block_number)
    if kind == "end":
        return (
            "0011" + FIRST_FIXED + "01" + area + "11" + FIRST_FIXED
            + "100" + date_field[3:14] + "11" + FIRST_FIXED
            + "101" + time_field[3:14] + "11"
        )

    fixed = FIRST_FIXED if signal_type == "first" else SECOND_FIXED
    return "1100" + fixed + "10" + area + "00" + fixed + date_field + fixed + time_field


def build_signal(
    kind: str,
    signal_type: str,
    area: str,
    when: datetime,
    blocks: int,
    medium: str = "tv_fm",
    leading_silence: float = 1.0,
) -> tuple[str, int]:
    if medium not in {"tv_fm", "mw_sw"}:
        raise ValueError("放送媒体が不正です")
    minimum = (10 if medium == "mw_sw" else 4) if kind == "start" else (4 if medium == "mw_sw" else 2)
    if blocks < minimum:
        raise ValueError(f"この信号のブロック数は{minimum}以上にしてください")
    # shortcut: PCM is assembled in memory; raise this with streaming WAV writes if longer files are needed.
    if blocks > MAX_BLOCKS:
        raise ValueError(f"一度に生成できるブロック数は{MAX_BLOCKS}以下です")
    if leading_silence < 1:
        raise ValueError("先頭の無信号期間は1秒以上にしてください")

    separator = "|" if kind == "end" else ""
    frame = "".join(build_block(kind, signal_type, area, when, n) + separator for n in range(1, blocks + 1))
    return frame, int(leading_silence * SAMPLE_RATE)


def preview_samples(block: str, bit_count: int = 4, points_per_bit: int = 64) -> list[float]:
    """Return downsampled PCM points from the start of one block for the GUI plot."""
    points = []
    phase = 0.0
    for bit in block[:bit_count]:
        frequency = 1024 if bit == "1" else 640
        step = 2 * math.pi * frequency / SAMPLE_RATE
        points.extend(
            int(32767 * 0.5 * math.sin(phase + step * round(i * SAMPLES_PER_BIT / points_per_bit))) / 32767
            for i in range(points_per_bit)
        )
        phase = (phase + step * SAMPLES_PER_BIT) % (2 * math.pi)
    return points


def signal_sample_count(bits: str, leading_silence_samples: int) -> int:
    return leading_silence_samples + (len(bits.replace("|", "")) + 92 * bits.count("|")) * SAMPLES_PER_BIT


def preview_bitstream(
    bits: str, leading_silence_samples: int, points: int, start_fraction: float = 0.0, span_fraction: float = 1.0
) -> list[str]:
    """Sample the complete transmission bit lane at the preview's horizontal resolution."""
    timeline = " " * (leading_silence_samples // SAMPLES_PER_BIT) + bits.replace("|", " " * 92)
    start = int(len(timeline) * start_fraction)
    span = max(1, int(len(timeline) * span_fraction))
    return [timeline[min(len(timeline) - 1, start + (2 * i + 1) * span // (2 * points))] for i in range(points)]


def preview_envelope(
    bits: str, leading_silence_samples: int, points: int = 1200,
    start_fraction: float = 0.0, span_fraction: float = 1.0,
) -> list[tuple[float, float]]:
    """Return an audio-amplitude envelope across the complete generated signal."""
    segments: list[tuple[int, int, bool]] = [(0, leading_silence_samples, False)]
    cursor = leading_silence_samples
    active_bits = 0
    for bit in bits:
        if bit == "|":
            if active_bits:
                end = cursor + active_bits * SAMPLES_PER_BIT
                segments.append((cursor, end, True))
                cursor = end
                active_bits = 0
            end = cursor + 92 * SAMPLES_PER_BIT
            segments.append((cursor, end, False))
            cursor = end
        else:
            active_bits += 1
    if active_bits:
        segments.append((cursor, cursor + active_bits * SAMPLES_PER_BIT, True))
        cursor += active_bits * SAMPLES_PER_BIT

    first = min(cursor - 1, int(cursor * start_fraction))
    visible_samples = max(1, min(cursor - first, int(cursor * span_fraction)))
    envelope = []
    segment_index = 0
    for i in range(points):
        start = first + i * visible_samples // points
        end = max(start + 1, first + (i + 1) * visible_samples // points)
        while segments[segment_index][1] <= start:
            segment_index += 1
        active = False
        j = segment_index
        while j < len(segments) and segments[j][0] < end:
            if segments[j][2]:
                active = True
                break
            j += 1
        envelope.append((-0.5, 0.5) if active else (0.0, 0.0))
    return envelope


def preview_pcm_waveform(
    bits: str, leading_silence_samples: int, points: int,
    start_fraction: float, span_fraction: float,
) -> list[float]:
    """Return actual PCM values sampled from a time window of the generated WAV."""
    segments = []
    cursor = leading_silence_samples
    phase = 0.0
    for bit in bits:
        if bit == "|":
            cursor += 92 * SAMPLES_PER_BIT
            phase = 0.0
            continue
        frequency = 1024 if bit == "1" else 640
        step = 2 * math.pi * frequency / SAMPLE_RATE
        segments.append((cursor, cursor + SAMPLES_PER_BIT, phase, step))
        phase = (phase + step * SAMPLES_PER_BIT) % (2 * math.pi)
        cursor += SAMPLES_PER_BIT

    total = signal_sample_count(bits, leading_silence_samples)
    first = min(total - 1, int(total * start_fraction))
    count = max(1, min(total - first, int(total * span_fraction)))
    sample_positions = (
        [first + round(i * (count - 1) / (points - 1)) for i in range(points)]
        if points > 1 else [first + count // 2]
    )
    result = []
    segment_index = 0
    for sample in sample_positions:
        while segment_index < len(segments) and segments[segment_index][1] <= sample:
            segment_index += 1
        if segment_index < len(segments) and segments[segment_index][0] <= sample:
            start, _end, phase, step = segments[segment_index]
            result.append(int(32767 * 0.5 * math.sin(phase + step * (sample - start))) / 32767)
        else:
            result.append(0.0)
    return result


def write_wav(path: Path, bits: str, leading_silence_samples: int, amplitude: float = 0.5) -> None:
    if not 0 < amplitude <= 1:
        raise ValueError("振幅は0より大きく1以下にしてください")

    samples = array("h", [0]) * leading_silence_samples
    phase = 0.0
    for bit in bits:
        if bit == "|":
            samples.extend(array("h", [0]) * (92 * SAMPLES_PER_BIT))
            phase = 0.0
            continue
        frequency = 1024 if bit == "1" else 640
        step = 2 * math.pi * frequency / SAMPLE_RATE
        samples.extend(
            int(32767 * amplitude * math.sin(phase + step * i))
            for i in range(SAMPLES_PER_BIT)
        )
        phase = (phase + step * SAMPLES_PER_BIT) % (2 * math.pi)

    path = path.resolve()
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temporary:
            temporary_path = temporary.name
        with wave.open(temporary_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(samples.tobytes())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
