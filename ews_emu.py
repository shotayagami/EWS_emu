"""Windows GUI for generating and inspecting EWS audio-signal WAV files."""

import tkinter as tk
import tempfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import winsound

from area_codes import AREAS
from digital_service_catalog import AREA_GROUPS, CATALOG_IS_LOCAL, SERVICES
from ews_digital import build_emergency_descriptor, write_descriptor
from ews_signal import AREA_COMMON, SAMPLE_RATE, build_block, build_signal, preview_bitstream, preview_envelope, preview_pcm_waveform, signal_sample_count, write_wav

BG, PANEL, EDGE = "#0e1318", "#171f27", "#2b3946"
TEXT, DIM, CYAN = "#e4ebf1", "#8795a3", "#6ad6ff"
FIELD_COLORS = ("#d99a37", "#3c829c", "#815baa", "#3c829c", "#398b64", "#3c829c", "#3f70a8")


def main() -> None:
    root = tk.Tk()
    root.title("EWS音声信号エミュレータ")
    root.geometry("1380x840")
    root.minsize(1080, 700)
    root.configure(background=BG)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=("Yu Gothic UI", 10))
    style.configure("TLabelframe", background=PANEL, foreground=TEXT, bordercolor=EDGE)
    style.configure("TLabelframe.Label", background=PANEL, foreground=DIM, font=("Yu Gothic UI", 10, "bold"))
    style.configure("TEntry", fieldbackground="#202a34", foreground=TEXT, insertcolor=TEXT)
    style.configure("TCombobox", fieldbackground="#202a34", foreground=TEXT, background="#202a34", arrowcolor=TEXT)
    style.map("TCombobox", fieldbackground=[("readonly", "#202a34")], foreground=[("readonly", TEXT)])
    style.configure("TButton", background="#263542", foreground=TEXT, padding=(8, 6))
    style.map("TButton", background=[("active", "#344b5d")])
    style.configure("Accent.TButton", background="#176b89", foreground="white", padding=(8, 8))
    style.map("Accent.TButton", background=[("active", "#2386a8")])

    signal = tk.StringVar(value="第一種開始")
    region = tk.StringVar(value=AREA_COMMON)
    signal_time = tk.StringVar(value=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"))
    blocks = tk.StringVar(value="4")
    medium = tk.StringVar(value="テレビ・FM")
    mode = tk.StringVar(value="音声FSK / WAV")
    area_name = tk.StringVar(value="地域共通")
    service_id = tk.StringVar(value="1")
    service_option = tk.StringVar()
    output = tk.StringVar(value="ews.wav")
    status = tk.StringVar(value="初期条件をプレビュー中")
    preview_data: dict | None = None
    view = {"start": 0.0, "span": 1.0, "drag": None}

    header = ttk.Frame(root, padding=(18, 14, 18, 10))
    header.pack(fill="x")
    ttk.Label(header, text="EWS 音声信号エミュレータ", font=("Yu Gothic UI", 17, "bold")).pack(side="left")
    ttk.Label(header, text="符号構成  /  CPFSK波形  /  PCM WAV", foreground=DIM).pack(side="right")

    body = ttk.Frame(root, padding=(14, 0, 14, 14))
    body.pack(fill="both", expand=True)
    controls = ttk.LabelFrame(body, text="生成条件", padding=14, width=340)
    controls.pack(side="left", fill="y")
    controls.pack_propagate(False)
    visual = tk.Canvas(body, bg=BG, highlightthickness=0)
    visual.pack(side="left", fill="both", expand=True, padx=(14, 0))
    time_controls = ttk.Frame(visual)
    ttk.Button(time_controls, text="全体表示", command=lambda: reset_view()).pack(side="left", padx=(0, 8))
    ttk.Label(time_controls, text="枠外ドラッグ:幅を保って移動  ·  枠内:移動  ·  端:幅調整").pack(side="left")
    status_label = ttk.Label(root, textvariable=status, anchor="w", padding=(18, 5), foreground=DIM)
    status_label.pack(fill="x", side="bottom")

    def row_label(row: int, text: str) -> None:
        ttk.Label(controls, text=text).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 3))

    row_label(0, "信号種別")
    ttk.Combobox(
        controls, textvariable=signal, state="readonly",
        values=("第一種開始", "第二種開始", "終了", "試験信号（第一種）", "試験信号（第二種）"), width=30,
    ).grid(row=1, column=0, columnspan=2, sticky="ew")
    row_label(2, "出力方式")
    mode_box = ttk.Combobox(controls, textvariable=mode, state="readonly", values=("音声FSK / WAV", "地上デジタル記述子"), width=30)
    mode_box.grid(row=3, column=0, columnspan=2, sticky="ew")
    row_label(4, "地域符号")
    area_box = ttk.Combobox(controls, textvariable=area_name, state="readonly", values=tuple(name for name, _ in AREAS), height=12)
    area_box.grid(row=5, column=0, columnspan=2, sticky="ew")
    row_label(6, "サービスID（ローカル資料）" if CATALOG_IS_LOCAL else "サービスID（デモ値）")
    service_box = ttk.Combobox(controls, textvariable=service_option, state="readonly", width=34)
    service_box.grid(row=7, column=0, columnspan=2, sticky="ew")
    row_label(8, "送出日時 (YYYY-MM-DD HH:MM)")
    date_entry = ttk.Entry(controls, textvariable=signal_time)
    date_entry.grid(row=9, column=0, columnspan=2, sticky="ew")
    row_label(10, "ブロック数")
    block_entry = ttk.Entry(controls, textvariable=blocks)
    block_entry.grid(row=11, column=0, columnspan=2, sticky="ew")
    row_label(12, "音声媒体")
    medium_box = ttk.Combobox(controls, textvariable=medium, state="readonly", values=("テレビ・FM", "中波・短波"), width=30)
    medium_box.grid(row=13, column=0, columnspan=2, sticky="ew")
    output_label = ttk.Label(controls, text="保存先")
    output_label.grid(row=14, column=0, columnspan=2, sticky="w", pady=(10, 3))
    ttk.Entry(controls, textvariable=output, width=28).grid(row=15, column=0, sticky="ew")

    def choose_output() -> None:
        path = filedialog.asksaveasfilename(
            title="出力ファイルの保存先", defaultextension=".wav" if mode.get().startswith("音声") else ".bin",
            filetypes=(("WAVファイル", "*.wav"),) if mode.get().startswith("音声") else (("記述子バイナリ", "*.bin"),),
            initialfile="ews.wav" if mode.get().startswith("音声") else "ews_descriptor.bin",
        )
        if path:
            output.set(path)

    ttk.Button(controls, text="参照…", command=choose_output).grid(row=15, column=1, padx=(6, 0))

    def area_changed(_event=None) -> None:
        region.set(dict(AREAS)[area_name.get()])
        refresh_service_options()
        update_preview()

    area_box.bind("<<ComboboxSelected>>", area_changed)

    service_ids_by_option: dict[str, int] = {}

    def refresh_service_options() -> None:
        allowed_groups = AREA_GROUPS[area_name.get()]
        groups = set(allowed_groups) if allowed_groups is not None else {group for group, _sid, _en, _ja in SERVICES}
        service_ids_by_option.clear()
        for group, sid, name_en, name_ja in SERVICES:
            if group not in groups:
                continue
            option = f"0x{sid:04X}  {name_ja}" + (f" ({name_en})" if CATALOG_IS_LOCAL else " [架空]")
            service_ids_by_option[option] = sid
        options = tuple(service_ids_by_option)
        service_box.configure(values=options)
        if options:
            service_option.set(options[0])
            service_id.set(str(service_ids_by_option[options[0]]))
        else:
            service_option.set("")
            service_id.set("")

    def service_changed(_event=None) -> None:
        if service_option.get() in service_ids_by_option:
            service_id.set(str(service_ids_by_option[service_option.get()]))
            update_preview()

    service_box.bind("<<ComboboxSelected>>", service_changed)

    def read_settings() -> dict:
        area = region.get().strip()
        if len(area) != 12 or any(bit not in "01" for bit in area):
            raise ValueError("地域符号は0と1の12桁で指定してください。")
        is_test = signal.get().startswith("試験信号")
        is_second = signal.get() in {"第二種開始", "試験信号（第二種）"}
        if mode.get().startswith("地上デジタル"):
            try:
                sid = int(service_id.get().strip())
            except ValueError as error:
                raise ValueError("選択地域に対応するサービスIDを選んでください。") from error
            descriptor = build_emergency_descriptor(sid, signal.get() not in {"終了"} and not is_test, is_second, area)
            path = Path(output.get().strip() or "ews_descriptor.bin")
            if path.suffix.lower() != ".bin":
                raise ValueError("記述子の拡張子は.binにしてください。")
            return {"digital": True, "test": is_test, "area": area, "path": path, "descriptor": descriptor, "sid": sid, "service_label": service_option.get()}
        block_count = int(blocks.get())
        kind = "end" if signal.get() == "終了" or is_test else "start"
        signal_type = "second" if is_second else "first"
        medium_code = "mw_sw" if medium.get() == "中波・短波" else "tv_fm"
        minimum = (10 if medium_code == "mw_sw" else 4) if kind == "start" else (4 if medium_code == "mw_sw" else 2)
        if block_count < minimum:
            raise ValueError(f"この条件ではブロック数を{minimum}以上にしてください。")
        when = datetime.strptime(signal_time.get().strip(), "%Y-%m-%d %H:%M").astimezone()
        output_text = output.get().strip()
        if not output_text:
            raise ValueError("WAV保存先を指定してください。")
        path = Path(output_text)
        if path.suffix.lower() != ".wav":
            raise ValueError("出力ファイルの拡張子は.wavにしてください。")
        bits, silence_samples = build_signal(kind, signal_type, area, when, block_count, medium=medium_code)
        first_block = build_block(kind, signal_type, area, when, 1)
        return {
            "digital": False, "test": is_test, "kind": kind, "signal": signal.get(), "area": area, "when": when,
            "blocks": block_count, "medium": medium.get(), "path": path,
            "bits": bits, "silence": silence_samples, "block": first_block,
        }

    def draw_preview(data: dict | None, error: str | None = None) -> None:
        visual.delete("all")
        w, h = max(visual.winfo_width(), 500), max(visual.winfo_height(), 300)
        if data is None:
            visual.create_text(w / 2, h / 2, text=error or "プレビューを更新してください", fill=DIM, font=("Yu Gothic UI", 14))
            return

        if data.get("digital"):
            visual.create_rectangle(10, 8, w - 10, h - 8, fill=PANEL, outline=EDGE)
            raw = data["descriptor"]
            visual.create_text(28, 30, text="地上デジタル 緊急情報記述子 (tag 0xFC)", anchor="nw", fill=TEXT, font=("Yu Gothic UI", 14, "bold"))
            values = (
                f"service_id: 0x{data['sid']:04X} ({data['sid']})  {data['service_label']}",
                f"start_end_flag: {int(not data['test'] and signal.get() != '終了')}  /  {'試験放送' if data['test'] else '開始・放送中' if signal.get() != '終了' else '終了'}",
                f"signal_level: {int(signal.get() in {'第二種開始', '試験信号（第二種）'})}  /  {'第二種' if signal.get() in {'第二種開始', '試験信号（第二種）'} else '第一種'}",
                f"area_code: {data['area']}  ({area_name.get()})",
                f"descriptor_length: {raw[1]} bytes  /  total: {len(raw)} bytes",
                "ローカルのTR-B14 6.7由来カタログです。現行の放送割当との一致は未確認です。" if CATALOG_IS_LOCAL else "サービスIDと局名は架空のデモ値です。実放送・実機試験には使用できません。",
                "試験放送はstart_end_flag=0。TS/PMT多重やTMCCフラグの時間変化は含みません。",
            )
            for i, value in enumerate(values):
                visual.create_text(30, 78 + 34 * i, text=value, anchor="nw", fill=DIM if i >= 5 else TEXT, font=("Consolas", 11 if i < 5 else 9))
            visual.create_text(30, 330, text="HEX", anchor="nw", fill=DIM, font=("Yu Gothic UI", 9, "bold"))
            visual.create_text(30, 356, text=" ".join(f"{byte:02X}" for byte in raw), anchor="nw", fill=CYAN, font=("Consolas", 16, "bold"))
            visual.create_text(30, 400, text="構成: tag · length · service_id · start_end_flag / signal_level / reserved · area_code_length · area_code / reserved", anchor="nw", fill=DIM, font=("Yu Gothic UI", 9))
            return

        def panel(y: int, height: int, title: str) -> None:
            visual.create_rectangle(10, y, w - 10, y + height, fill=PANEL, outline=EDGE)
            visual.create_text(26, y + 13, text=title, anchor="nw", fill=DIM, font=("Yu Gothic UI", 10, "bold"))

        kind = data["kind"]
        block = data["block"]
        blocks_count = data["blocks"]
        data_bits = 100 if kind == "start" else 192
        block_seconds = data_bits / 64
        duration = signal_sample_count(data["bits"], data["silence"]) / SAMPLE_RATE
        start_fraction, span_fraction = view["start"], view["span"]
        end_fraction = min(1.0, start_fraction + span_fraction)
        start_seconds, end_seconds = start_fraction * duration, end_fraction * duration
        panel(8, 70, "信号概要")
        stats = (
            ("種別 / 地域", f"{data['signal']}   {data['area']}"),
            ("ブロック / 長さ", f"{blocks_count} × {block_seconds:.4f}s   計 {duration:.2f}s"),
            ("変調", "CPFSK  /  64 bit/s"),
            ("WAV", "48 kHz  /  16 bit  /  mono"),
        )
        gap, left, right = 8, 20, w - 20
        card_w = (right - left - gap * 3) / 4
        for i, (label, value) in enumerate(stats):
            x = left + i * (card_w + gap)
            visual.create_text(x, 42, text=label, anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
            visual.create_text(x, 59, text=value, anchor="nw", fill=TEXT, font=("Yu Gothic UI", 9, "bold"))

        panel(88, 145, "ブロック1  /  100 bit")
        fields = (("前置", 0, 4), ("固定", 4, 20), ("地域", 20, 36), ("固定", 36, 52), ("月日", 52, 68), ("固定", 68, 84), ("年時", 84, 100))
        x0, x1 = 28, w - 28
        bit_w = (x1 - x0) / 100
        for index, (label, start, end) in enumerate(fields):
            x = x0 + start * bit_w
            width = (end - start) * bit_w
            visual.create_text(x + width / 2, 126, text=label, fill=DIM, font=("Consolas", 8, "bold"))
            visual.create_rectangle(x, 140, x + width, 180, fill=FIELD_COLORS[index], outline=BG)
            for bit_index in range(start, end):
                cx = x0 + (bit_index + 0.5) * bit_w
                visual.create_text(cx, 160, text=block[bit_index], fill="white", font=("Consolas", max(6, min(9, int(bit_w))), "bold"))
            if index:
                visual.create_line(x, 137, x, 183, fill=BG, width=2)
        visual.create_text(x0, 194, text="前置4  ·  固定16  ·  地域16  ·  固定16  ·  月日16  ·  固定16  ·  年時16", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))

        panel(242, 300, "音声波形  /  全体の送出区間とPCM波形")
        wave_left, wave_right = 54, w - 28
        visual.create_text(wave_right, 267, text="全送出時間のビット列とPCM音声波形", anchor="ne", fill=TEXT, font=("Yu Gothic UI", 9))
        overview_top, overview_bottom = 294, 318
        overview_mid = (overview_top + overview_bottom) / 2
        visual.create_text(wave_left, 286, text="0 s", anchor="sw", fill=DIM, font=("Consolas", 8))
        visual.create_text(wave_right, 286, text=f"{duration:.2f} s", anchor="se", fill=DIM, font=("Consolas", 8))
        visual.create_line(wave_left, overview_mid, wave_right, overview_mid, fill=EDGE)
        overview = preview_envelope(data["bits"], data["silence"], max(200, int(wave_right - wave_left)))
        for i, (_, high) in enumerate(overview):
            if high:
                x0 = wave_left + i * (wave_right - wave_left) / len(overview)
                x1 = wave_left + (i + 1) * (wave_right - wave_left) / len(overview)
                visual.create_rectangle(x0, overview_mid - 5, x1, overview_mid + 5, fill=CYAN, outline="")
        if span_fraction < 1:
            view_x0 = wave_left + start_fraction * (wave_right - wave_left)
            view_x1 = wave_left + end_fraction * (wave_right - wave_left)
            visual.create_rectangle(view_x0, overview_top - 3, view_x1, overview_bottom + 3, outline="#f0c040", dash=(3, 2))
            visual.create_rectangle(view_x0 - 3, overview_top - 3, view_x0 + 3, overview_bottom + 3, fill="#f0c040", outline="")
            visual.create_rectangle(view_x1 - 3, overview_top - 3, view_x1 + 3, overview_bottom + 3, fill="#f0c040", outline="")
        marker_fraction = data["silence"] / SAMPLE_RATE / duration
        if start_fraction <= marker_fraction <= end_fraction:
            leading_x = wave_left + (marker_fraction - start_fraction) / span_fraction * (wave_right - wave_left)
            visual.create_line(leading_x, overview_top - 3, leading_x, overview_bottom + 3, fill="#f0c040", dash=(3, 3))
        visual.create_text(wave_left, 326, text=f"{start_seconds:.3f} s", anchor="nw", fill=DIM, font=("Consolas", 8))
        visual.create_text(wave_right, 326, text=f"{end_seconds:.3f} s", anchor="ne", fill=DIM, font=("Consolas", 8))

        visual.create_text(wave_left, 345, text="送信ビット列（選択範囲）", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
        bit_top, bit_bottom = 354, 381
        bit_high, bit_mid, bit_low = bit_top + 3, (bit_top + bit_bottom) / 2, bit_bottom - 3
        bit_samples = preview_bitstream(
            data["bits"], data["silence"], max(200, int(wave_right - wave_left)), start_fraction, span_fraction
        )
        bit_coords = [wave_left, bit_mid if bit_samples[0] == " " else bit_high if bit_samples[0] == "1" else bit_low]
        previous_y = bit_coords[1]
        for i, bit in enumerate(bit_samples[1:], start=1):
            x = wave_left + i * (wave_right - wave_left) / len(bit_samples)
            y = bit_mid if bit == " " else bit_high if bit == "1" else bit_low
            bit_coords.extend((x, previous_y, x, y))
            previous_y = y
        bit_coords.append(wave_right)
        bit_coords.append(previous_y)
        visual.create_line(*bit_coords, fill="#f0c040", width=1.5)

        pcm_top, pcm_bottom = 405, 478
        pcm_mid = (pcm_top + pcm_bottom) / 2
        sample_points = min(
            5000, max(2, int(wave_right - wave_left) * 4),
            max(2, int(duration * span_fraction * SAMPLE_RATE)),
        )
        pcm_detail = duration * span_fraction <= sample_points / (4 * 1024)
        pcm_label = "PCM波形（実PCMサンプル）" if pcm_detail else "PCM振幅包絡（ズームすると実PCMサンプル表示）"
        visual.create_text(wave_left, 390, text=pcm_label, anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
        for y, label in ((pcm_top, "+0.5"), (pcm_mid, "0"), (pcm_bottom, "−0.5")):
            visual.create_line(wave_left, y, wave_right, y, fill=EDGE)
            visual.create_text(wave_left - 6, y, text=label, anchor="e", fill=DIM, font=("Consolas", 8))
        # shortcut: use an amplitude envelope for wide ranges, draw sampled PCM after zooming in.
        if pcm_detail:
            samples = preview_pcm_waveform(data["bits"], data["silence"], sample_points, start_fraction, span_fraction)
            coords = []
            for i, value in enumerate(samples):
                x = wave_left + i * (wave_right - wave_left) / (len(samples) - 1)
                coords.extend((x, pcm_mid - value * (pcm_bottom - pcm_top)))
            visual.create_line(*coords, fill=CYAN, width=1.5, smooth=False)
        else:
            envelope = preview_envelope(
                data["bits"], data["silence"], max(200, int(wave_right - wave_left)), start_fraction, span_fraction
            )
            for i, (low, high) in enumerate(envelope):
                x = wave_left + i * (wave_right - wave_left) / (len(envelope) - 1)
                y0 = pcm_mid - high * (pcm_bottom - pcm_top)
                y1 = pcm_mid - low * (pcm_bottom - pcm_top)
                visual.create_line(x, y0, x, y1, fill=CYAN, width=1)
        visual.create_text(wave_left, 489, text="黄線: 表示範囲の送信ビット列  ·  青線: PCM振幅", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
        visual.create_text(wave_left, 512, text=f"選択範囲 {start_seconds:.3f}–{end_seconds:.3f} s  ·  拡大時はWAVと同じPCMサンプルを表示", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
        visual.create_window(wave_left + 4, 540, anchor="sw", window=time_controls)

        panel(554, max(74, h - 570), "送出構成")
        silent = 1.0
        active = blocks_count * block_seconds
        visual.create_text(28, 588, text=f"先頭無信号 {silent:.2f}s   →   100 bit × {blocks_count} ブロック", anchor="nw", fill=TEXT, font=("Yu Gothic UI", 9))
        if kind == "end":
            visual.create_text(28, 610, text=f"終了信号は各ブロック後に92 bitの無音を挿入   ·   送出長 {duration:.2f}s", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
            if data["test"]:
                visual.create_text(28, 632, text="試験用は終了信号と同じ波形です。運用では前後に機能確認用である旨の放送が必要です（このWAVに音声告知は含みません）。", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))
        else:
            visual.create_text(28, 610, text=f"連続送出 {active:.2f}s   ·   地域コードは12 bit   ·   偶数ブロックは告示の日時補正を適用", anchor="nw", fill=DIM, font=("Yu Gothic UI", 8))

    def zoom_view(factor: float, anchor: float = 0.5) -> None:
        if preview_data is None or preview_data.get("digital"):
            return
        duration = signal_sample_count(preview_data["bits"], preview_data["silence"]) / SAMPLE_RATE
        old_span = view["span"]
        new_span = max(min(1.0, 0.005 / duration), min(1.0, old_span / factor))
        center = view["start"] + anchor * old_span
        view["span"] = new_span
        view["start"] = max(0.0, min(1.0 - new_span, center - anchor * new_span))
        draw_preview(preview_data)

    def reset_view() -> None:
        view.update(start=0.0, span=1.0, drag=None)
        if preview_data is not None:
            draw_preview(preview_data)

    def begin_view_drag(event) -> None:
        if preview_data is None or preview_data.get("digital") or not 294 <= event.y <= 480:
            return
        width = max(visual.winfo_width(), 500) - 82
        position = max(0.0, min(1.0, (event.x - 54) / width))
        left, right = view["start"], view["start"] + view["span"]
        if 294 <= event.y <= 318:
            left_x, right_x = 54 + left * width, 54 + right * width
            if abs(event.x - left_x) <= 9:
                drag_mode = "left"
            elif abs(event.x - right_x) <= 9:
                drag_mode = "right"
            elif left_x < event.x < right_x and view["span"] < 0.999:
                drag_mode = "move"
            else:
                drag_mode = "jump"
        else:
            drag_mode = "move"
        view["drag"] = (drag_mode, event.x, left, view["span"])
        visual.configure(cursor="crosshair" if drag_mode == "select" else "sb_h_double_arrow")
        if drag_mode == "jump":
            view["start"] = max(0.0, min(1.0 - view["span"], position - view["span"] / 2))
            draw_preview(preview_data)

    def move_view_drag(event) -> None:
        if view["drag"] is None or preview_data is None:
            return
        mode_name, initial_x, initial_start, initial_span = view["drag"]
        width = max(visual.winfo_width(), 500) - 82
        current = max(0.0, min(1.0, (event.x - 54) / width))
        duration = signal_sample_count(preview_data["bits"], preview_data["silence"]) / SAMPLE_RATE
        minimum = min(1.0, 0.005 / duration)
        if mode_name == "jump":
            view["start"] = max(0.0, min(1.0 - initial_span, current - initial_span / 2))
            view["span"] = initial_span
        elif mode_name == "left":
            end = initial_start + initial_span
            view["start"] = min(current, end - minimum)
            view["span"] = end - view["start"]
        elif mode_name == "right":
            view["start"] = initial_start
            view["span"] = max(minimum, min(1.0 - initial_start, current - initial_start))
        else:
            view["start"] = max(0.0, min(1.0 - initial_span, initial_start + (event.x - initial_x) / width))
            view["span"] = initial_span
        draw_preview(preview_data)

    def update_cursor(event) -> None:
        if preview_data is None or preview_data.get("digital"):
            visual.configure(cursor="arrow")
            return
        if view["drag"]:
            mode_name = view["drag"][0]
            cursor = "sb_h_double_arrow"
        elif 294 <= event.y <= 318:
            width = max(visual.winfo_width(), 500) - 82
            x = event.x
            left_x = 54 + view["start"] * width
            right_x = 54 + (view["start"] + view["span"]) * width
            if min(abs(x - left_x), abs(x - right_x)) <= 9:
                cursor = "sb_h_double_arrow"
            elif left_x < x < right_x and view["span"] < 0.999:
                cursor = "sb_h_double_arrow"
            else:
                cursor = "sb_h_double_arrow"
        elif 340 <= event.y <= 480:
            cursor = "sb_h_double_arrow"
        else:
            cursor = "arrow"
        visual.configure(cursor=cursor)

    def end_view_drag(event) -> None:
        view["drag"] = None
        update_cursor(event)

    def on_mousewheel(event):
        if 286 <= event.y <= 482:
            width = max(visual.winfo_width(), 500) - 82
            anchor = max(0.0, min(1.0, (event.x - 54) / width))
            zoom_view(1.25 if event.delta > 0 else 0.8, anchor)
            return "break"

    def update_preview() -> dict | None:
        nonlocal preview_data
        try:
            preview_data = read_settings()
        except ValueError as error:
            preview_data = None
            status.set(f"入力を確認: {error}")
            draw_preview(None, str(error))
            return None
        if not preview_data.get("digital"):
            duration = signal_sample_count(preview_data["bits"], preview_data["silence"]) / SAMPLE_RATE
            view["span"] = min(1.0, 0.5 / duration)
            view["start"] = min(1.0 - view["span"], preview_data["silence"] / SAMPLE_RATE / duration)
            view["drag"] = None
        else:
            view.update(start=0.0, span=1.0, drag=None)
        draw_preview(preview_data)
        status.set("プレビュー更新済み。WAVを保存するか、条件を変更してください。")
        return preview_data

    def generate() -> None:
        data = update_preview()
        if data is None:
            return
        path = data["path"]
        if path.exists() and not messagebox.askyesno("上書き確認", f"既存のファイルを上書きしますか？\n{path}", parent=root):
            status.set("保存をキャンセルしました")
            return
        try:
            if data.get("digital"):
                write_descriptor(path, data["descriptor"])
            else:
                write_wav(path, data["bits"], data["silence"])
        except (OSError, ValueError) as error:
            status.set(f"保存できませんでした: {error}")
            messagebox.showerror("生成できませんでした", str(error), parent=root)
            return
        status.set(f"ファイルを保存しました: {path}")
        messagebox.showinfo("生成完了", f"ファイルを保存しました。\n{path}", parent=root)

    def play() -> None:
        data = update_preview()
        if data is None or data.get("digital"):
            return
        stop_playback()
        handle, name = tempfile.mkstemp(suffix=".wav", prefix="ews_preview_")
        import os
        os.close(handle)
        playback_file[0] = Path(name)
        try:
            write_wav(playback_file[0], data["bits"], data["silence"])
            winsound.PlaySound(str(playback_file[0]), winsound.SND_FILENAME | winsound.SND_ASYNC)
            status.set("生成したWAVを再生中です。停止ボタンで止められます。")
            playback_path = playback_file[0]
            root.after(int((data["silence"] / SAMPLE_RATE + len(data["bits"]) / 64) * 1000) + 500, lambda p=playback_path: cleanup_playback(p))
        except (OSError, RuntimeError) as error:
            cleanup_playback()
            messagebox.showerror("再生できませんでした", str(error), parent=root)

    playback_file: list[Path | None] = [None]

    def cleanup_playback(expected: Path | None = None) -> None:
        if playback_file[0] is not None and (expected is None or playback_file[0] == expected):
            playback_file[0].unlink(missing_ok=True)
            playback_file[0] = None

    def stop_playback() -> None:
        winsound.PlaySound(None, 0)
        cleanup_playback()
        status.set("再生を停止しました")

    def mode_changed(_event=None) -> None:
        digital = mode.get().startswith("地上デジタル")
        if digital:
            output.set("ews_descriptor.bin")
        else:
            output.set("ews.wav")
        output_label.configure(text="記述子保存先" if digital else "WAV保存先")
        block_entry.configure(state="disabled" if digital else "normal")
        medium_box.configure(state="disabled" if digital else "readonly")
        date_entry.configure(state="disabled" if digital else "normal")
        service_box.configure(state="readonly")
        play_button.configure(state="disabled" if digital else "normal")
        update_preview()

    mode_box.bind("<<ComboboxSelected>>", mode_changed)
    ttk.Button(controls, text="プレビュー更新", command=update_preview).grid(row=16, column=0, columnspan=2, sticky="ew", pady=(18, 5))
    play_button = ttk.Button(controls, text="▶ 再生", command=play)
    play_button.grid(row=17, column=0, sticky="ew", padx=(0, 3))
    ttk.Button(controls, text="■ 停止", command=stop_playback).grid(row=17, column=1, sticky="ew", padx=(3, 0))
    ttk.Button(controls, text="生成・保存", style="Accent.TButton", command=generate).grid(row=18, column=0, columnspan=2, sticky="ew", pady=(5, 0))
    ttk.Label(
        controls,
        text="WAV再生時、近くのEWS対応受信機が反応する場合があります。電波送信機能はありません。",
        wraplength=285, foreground=DIM,
    ).grid(row=19, column=0, columnspan=2, sticky="w", pady=(16, 0))
    controls.columnconfigure(0, weight=1)

    def redraw(_event=None) -> None:
        if preview_data is not None:
            draw_preview(preview_data)

    visual.bind("<Configure>", redraw)
    visual.bind("<ButtonPress-1>", begin_view_drag)
    visual.bind("<B1-Motion>", move_view_drag)
    visual.bind("<ButtonRelease-1>", end_view_drag)
    visual.bind("<MouseWheel>", on_mousewheel)
    visual.bind("<Double-Button-1>", lambda _event: reset_view())
    visual.bind("<Motion>", update_cursor)
    visual.bind("<Leave>", lambda _event: visual.configure(cursor="arrow"))
    root.protocol("WM_DELETE_WINDOW", lambda: (stop_playback(), root.destroy()))
    refresh_service_options()
    mode_changed()
    root.mainloop()


if __name__ == "__main__":
    main()
