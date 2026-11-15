import tempfile
import unittest
import wave
from datetime import datetime
from pathlib import Path

from ews_signal import AREA_COMMON, SECOND_FIXED, build_block, build_signal, preview_samples, write_wav


class EwsSignalTests(unittest.TestCase):
    def test_start_end_blocks_and_midnight_boundary(self) -> None:
        sent = datetime(2026, 11, 14, 23, 55)
        start = build_block("start", "first", AREA_COMMON, sent, 1)
        next_block = build_block("start", "first", AREA_COMMON, sent, 2)
        second = build_block("start", "second", AREA_COMMON, sent, 1)
        end = build_block("end", "first", AREA_COMMON, sent, 1)
        self.assertEqual((len(start), len(next_block), len(end)), (100, 100, 100))
        self.assertTrue(start.startswith("1100"))
        self.assertTrue(second.startswith("1100" + SECOND_FIXED))
        self.assertTrue(end.startswith("0011"))
        self.assertEqual(next_block[52:68], "010" + "11110" + "1" + "11011" + "00")
        self.assertEqual(next_block[84:100], "011" + "00011" + "1" + "01101" + "00")

    def test_waveform_preview_matches_four_bits(self) -> None:
        block = build_block("start", "first", AREA_COMMON, datetime(2026, 11, 14, 12, 0), 1)
        samples = preview_samples(block)
        self.assertEqual(len(samples), 4 * 64)
        self.assertGreater(max(samples), 0.49)
        self.assertLess(min(samples), -0.49)

    def test_end_wav_has_silent_interblock_period(self) -> None:
        bits, lead = build_signal("end", "first", AREA_COMMON, datetime(2026, 11, 14, 12, 0), 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "end.wav"
            write_wav(path, bits, lead)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 48_000))
                self.assertEqual(wav.getnframes(), 48_000 + 2 * 192 * 750)
                wav.setpos(48_000 + 100 * 750)
                self.assertEqual(set(wav.readframes(92 * 750)), {0})


if __name__ == "__main__":
    unittest.main()
