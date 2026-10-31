# SPDX-License-Identifier: GPL-3.0-or-later
#
# Experimental SmartMonitor `.ui` -> `img.dat` compiler for the currently
# reversed subset of widget/resource types.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from library.log import logger
from library.smartmonitor_imgdat import (
    SMARTMONITOR_RECORD_SLOT_SIZE,
    pack_record_fields,
    parse_imgdat_file,
    resource_payload_size,
)

from library.smartmonitor_render import (
    render_datetime_preview_payload,
    render_number_glyph_payload,
    render_static_text_payload,
    render_datetime_text_payload
)
from library.smartmonitor_ui import (
    SmartMonitorThemeBundle,
    Widget,
    WidgetParent,
    detect_frame_count,
    parse_theme_bundle,
    resolve_theme_path,
)

SMARTMONITOR_DEFAULT_SLOT_COUNT = 150

@dataclass(slots=True)
class CompiledSmartMonitorRecord:
    record_type: int
    fields: dict[str, Any]


def align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        return value
    return ((value + alignment - 1) // alignment) * alignment


def rgb24_to_rgb565(color: int) -> int:
    return ((color >> 8) & 0xF800) | ((color >> 5) & 0x07E0) | ((color >> 3) & 0x001F)


def _frame_paths(base_dir: str | Path, raw_path: str) -> list[Path]:
    path = resolve_theme_path(base_dir, raw_path)
    count = detect_frame_count(base_dir, raw_path)
    if count <= 1:
        return [path]

    stem = path.stem
    suffix = path.suffix
    digit_count = 0
    for char in reversed(stem):
        if not char.isdigit():
            break
        digit_count += 1
    prefix = stem[:-digit_count] if digit_count else stem
    return [path.with_name(f"{prefix}{index:0{digit_count}d}{suffix}") for index in range(count)]


def _image_to_rgb565_bytes(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    out = bytearray()
    for red, green, blue in rgb.getdata():
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        out.extend(value.to_bytes(2, "little"))
    return bytes(out)


def _image_to_rgba565_payload(image: Image.Image) -> bytes:
    rgba = image.convert("RGBA")
    alpha = bytearray()
    color = bytearray()
    for red, green, blue, alpha_value in rgba.getdata():
        alpha.append(alpha_value)
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        color.extend(value.to_bytes(2, "little"))
    return bytes(alpha + color)


def _load_frame_payloads(
    base_dir: str | Path,
    raw_path: str,
    width: int,
    height: int,
) -> tuple[bytes, int, bool]:
    paths = _frame_paths(base_dir, raw_path)
    is_png = Path(raw_path).suffix.lower() == ".png"
    payload = bytearray()
    for frame_path in paths:
        image = Image.open(frame_path)
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        if is_png:
            payload.extend(_image_to_rgba565_payload(image))
        else:
            payload.extend(_image_to_rgb565_bytes(image))
    return bytes(payload), len(paths), is_png


def _startup_record(bundle: SmartMonitorThemeBundle, offset: int) -> tuple[CompiledSmartMonitorRecord, bytes] | None:
    startup = bundle.startup_pic
    if startup is None or not startup.path:
        return None
    parent = bundle.theme.widget_parents[0] if bundle.theme.widget_parents else None
    width = parent.geometry.width if parent else 0
    height = parent.geometry.height if parent else 0
    payload, frame_count, _ = _load_frame_payloads(bundle.base_dir, startup.path, width, height)
    record = CompiledSmartMonitorRecord(
        record_type=0x94,
        fields={
            "reserved_1": 0,
            "reserved_2": 0,
            "x": 0,
            "y": 0,
            "width": width,
            "height": height,
            "asset_offset": offset,
            "frame_count": frame_count,
            "total_ms": startup.total_ms,
            "delay_ms": startup.delay_ms,
            "background_color_rgb565": rgb24_to_rgb565(startup.bg_color & 0xFFFFFF),
        },
    )
    return record, payload


def _background_record(
    bundle: SmartMonitorThemeBundle,
    parent: WidgetParent,
    offset: int,
) -> tuple[CompiledSmartMonitorRecord, bytes] | None:
    if not parent.background_image_path:
        return None
    width = parent.geometry.width
    height = parent.geometry.height
    payload, frame_count, is_png = _load_frame_payloads(
        bundle.base_dir,
        parent.background_image_path,
        width,
        height,
    )
    record = CompiledSmartMonitorRecord(
        record_type=0x81,
        fields={
            "reserved_1": 0,
            "reserved_2": 0,
            "x": 0,
            "y": 0,
            "width": width,
            "height": height,
            "background_mode_flag": int(parent.background_type == 0),
            "background_color_rgb565": rgb24_to_rgb565(parent.background_color & 0xFFFFFF),
            "asset_offset": offset,
            "frame_count": frame_count,
            "is_png": is_png,
            "image_delay": parent.image_delay,
        },
    )
    return record, payload


def _image_widget_record(
    bundle: SmartMonitorThemeBundle,
    widget: Widget,
    offset: int,
) -> tuple[CompiledSmartMonitorRecord, bytes]:
    image_path = str(widget.raw_fields.get("imagePath", ""))
    payload, frame_count, is_png = _load_frame_payloads(
        bundle.base_dir,
        image_path,
        widget.geometry.width,
        widget.geometry.height,
    )
    record = CompiledSmartMonitorRecord(
        record_type=0x84,
        fields={
            "widget_id": widget.global_id + 1,
            "reserved_2": 0,
            "x": widget.geometry.x,
            "y": widget.geometry.y,
            "width": widget.geometry.width,
            "height": widget.geometry.height,
            "asset_offset": offset,
            "frame_count": frame_count,
            "is_png": is_png,
            "delay_ms": int(widget.raw_fields.get("imageDelay", "0") or 0),
        },
    )
    return record, payload


def _progress_bar_record(widget: Widget) -> CompiledSmartMonitorRecord:
    style = widget.style
    return CompiledSmartMonitorRecord(
        record_type=0x8B,
        fields={
            "widget_id": widget.global_id + 1,
            "fast_sensor": widget.sensor.fast_sensor if widget.sensor else 0,
            "x": widget.geometry.x,
            "y": widget.geometry.y,
            "width": widget.geometry.width,
            "height": widget.geometry.height,
            "show_type": int(style.show_type if style else 1),
            "bg_color_rgb565": rgb24_to_rgb565((style.bg_color if style else 0) & 0xFFFFFF),
            "fg_color_rgb565": rgb24_to_rgb565((style.fg_color if style else 0) & 0xFFFFFF),
            "frame_color_rgb565": rgb24_to_rgb565((style.frame_color if style else 0) & 0xFFFFFF),
            "bg_image_width": 0,
            "bg_image_height": 0,
            "bg_image_offset": 0,
            "fg_image_width": 0,
            "fg_image_height": 0,
            "fg_image_offset": 0,
        },
    )


def _datetime_glyph_charset(widget: Widget) -> str:
    fmt = (widget.datetime_format or "").lower()
    separator = ":"
    for candidate in (":", "-", "/", "."):
        if candidate in fmt:
            separator = candidate
            break
    return f"0123456789{separator}"

def _datetime_preview_kind(preview: str) -> str:
    normalized = (preview or "").strip().lower()
    has_time = ":" in normalized
    has_date = any(separator in normalized for separator in ("-", "/", "."))
    if has_time and has_date:
        return "datetime"
    if has_date:
        return "date"
    return "time"

def _datetime_format_preview(widget: Widget) -> str:
    fmt = (widget.datetime_format or "").lower()
    mapping = {
        "y": "1",
        "m": "2",
        "d": "3",
        "h": "4",
        "n": "5",
        "s": "6",
    }
    preview_chars: list[str] = []
    previous: str | None = None
    for char in fmt:
        if char in mapping:
            mapped = mapping[char]
            if mapped != previous:
                preview_chars.append(mapped)
                previous = mapped
            continue
        if previous != char:
            preview_chars.append(char)
            previous = char
    preview = "".join(preview_chars).strip()
    if not preview:
        preview = "4:5:6"
    if preview.startswith("4") and not any(digit in preview for digit in ("1", "2", "3")):
        preview = f" {preview}"
    return preview

def _datetime_widget_record(
    bundle: SmartMonitorThemeBundle,
    widget: Widget,
    offset: int,
) -> tuple[CompiledSmartMonitorRecord, bytes]:

    preview = _datetime_format_preview(widget)

    '''DEFAULT_TIME_NUMBER_GLYPHS = "0123456789"
    SPECIAL_TIME_GLYPHS = ".-/ :PROFi"

    font = _resolve_font(widget.font, widget.font.size)
    img, bmp_w, bmp_h = render_vertical_text(DEFAULT_TIME_NUMBER_GLYPHS, font)

    payload = bytearray(img.tobytes())

    glyph_widths = []

    for ch in SPECIAL_TIME_GLYPHS:
        img, w, h = render_single_glyph(ch, font)
        glyph_widths.append(w)
        zero_bytes = b'\x00'*(w*(bmp_h-h))
        payload.extend(bytes(zero_bytes))
        payload.extend(img.tobytes())'''

    glyph_bitmap_width, glyph_bitmap_height, glyph_widths, payload = render_datetime_text_payload(widget.font)

    font_color = widget.font.color if widget.font else 0
    record = CompiledSmartMonitorRecord(
        record_type=0x8E,
        fields={
            "widget_id": widget.global_id + 1,
            "time_command": 0x15,
            "x": widget.geometry.x,
            "y": widget.geometry.y,
            "width": widget.geometry.width,
            "height": widget.geometry.height,
            "h_align": int(widget.raw_fields.get("hAlign", 0) or 0),
            "font_color_rgb565": rgb24_to_rgb565(font_color & 0xFFFFFF),
            "font_alpha": (font_color >> 24) & 0xFF,
            "glyph_bitmap_offset": offset,
            "glyph_bitmap_height": glyph_bitmap_height,
            "glyph_bitmap_width": glyph_bitmap_width,
            "glyph_widths": glyph_widths,
            "format_preview": preview,
        },
    )
    return record, bytes(payload)

def _number_widget_record(widget: Widget, offset: int) -> tuple[CompiledSmartMonitorRecord, bytes]:
    glyph_widths, glyph_height, payload = render_number_glyph_payload(widget.font, gamma=1.4)
    font_color = widget.font.color if widget.font else 0
    record = CompiledSmartMonitorRecord(
        record_type=0x92,
        fields={
            "widget_id": widget.global_id + 1,
            "fast_sensor": widget.sensor.fast_sensor if widget.sensor else 0,
            "x": widget.geometry.x,
            "y": widget.geometry.y,
            "width": widget.geometry.width,
            "height": widget.geometry.height,
            "h_align": int(widget.raw_fields.get("hAlign", 0) or 0),
            "font_color_rgb565": rgb24_to_rgb565(font_color & 0xFFFFFF),
            "is_div_1204": bool(widget.sensor and widget.sensor.is_div_1204),
            "font_alpha": (font_color >> 24) & 0xFF,
            "glyph_bitmap_offset": offset,
            "glyph_bitmap_height": glyph_height,
            "glyph_widths": glyph_widths,
        },
    )
    return record, payload


def _static_text_record(widget: Widget, offset: int) -> tuple[CompiledSmartMonitorRecord, bytes]:
    text = widget.font.text if widget.font else ""
    rendered = render_static_text_payload(
        text,
        widget.font,
        vendor_mode=True,
        binary_threshold=160,
    )
    font_color = widget.font.color if widget.font else 0
    record = CompiledSmartMonitorRecord(
        record_type=0x93,
        fields={
            "widget_id": widget.global_id + 1,
            "reserved_2": 0,
            "x": widget.geometry.x,
            "y": widget.geometry.y,
            "rendered_width": rendered.width,
            "rendered_height": rendered.height,
            "text_bitmap_offset": offset,
            "font_color_rgb565": rgb24_to_rgb565(font_color & 0xFFFFFF),
            "font_alpha": (font_color >> 24) & 0xFF,
        },
    )
    return record, rendered.payload


def compile_theme_bundle(bundle: SmartMonitorThemeBundle) -> bytes:
    pending_records: list[tuple[CompiledSmartMonitorRecord, bytes]] = []

    startup_entry = _startup_record(bundle, 0)
    if startup_entry is not None:
        pending_records.append(startup_entry)

    for parent in bundle.theme.widget_parents:
        entry = _background_record(bundle, parent, 0)
        if entry is not None:
            pending_records.append(entry)

    for widget in bundle.theme.widgets:
        if widget.widget_type == 4:
            pending_records.append(_image_widget_record(bundle, widget, 0))
        elif widget.widget_type == 3:
            pending_records.append((_progress_bar_record(widget), b""))
        elif widget.widget_type == 6:
            pending_records.append(_datetime_widget_record(bundle, widget, 0))
        elif widget.widget_type == 5:
            pending_records.append(_number_widget_record(widget, 0))
        elif widget.widget_type == 2:
            pending_records.append(_static_text_record(widget, 0))
        else:
            logger.warning(
                "Skipping unsupported SmartMonitor widget type %s (%s) in %s",
                widget.widget_type,
                widget.object_name or f"id={widget.global_id}",
                bundle.ui_path,
            )
            continue

    resource_start = align_up(max(0x1000, (len(pending_records) + 1) * SMARTMONITOR_RECORD_SLOT_SIZE), 0x1000)
    resource_cache: dict[bytes, int] = {}
    resources = bytearray()
    finalized_records: list[CompiledSmartMonitorRecord] = []

    allocation_priority = {
        0x94: 0,
        0x81: 1,
        0x84: 2,
        0x93: 3,
        0x92: 4,
        0x8E: 4,
    }
    allocated_offsets: dict[int, int] = {}
    for index, (record, payload) in sorted(
        enumerate(pending_records),
        key=lambda item: (allocation_priority.get(item[1][0].record_type, 999), item[0]),
    ):
        cached_offset = resource_cache.get(payload)
        if cached_offset is None:
            cached_offset = resource_start + len(resources)
            resource_cache[payload] = cached_offset
            resources.extend(payload)
        allocated_offsets[index] = cached_offset

    for index, (record, _payload) in enumerate(pending_records):
        cached_offset = allocated_offsets[index]
        fields = dict(record.fields)
        for key in ("asset_offset", "glyph_bitmap_offset", "text_bitmap_offset"):
            if key in fields:
                fields[key] = cached_offset
        finalized_records.append(CompiledSmartMonitorRecord(record.record_type, fields))

    output = bytearray(resource_start + len(resources))
    output[0:4] = SMARTMONITOR_DEFAULT_SLOT_COUNT.to_bytes(4, "little")

    for index, record in enumerate(finalized_records, start=1):
        start = index * SMARTMONITOR_RECORD_SLOT_SIZE
        output[start:start + SMARTMONITOR_RECORD_SLOT_SIZE] = pack_record_fields(record.record_type, record.fields)

    output[resource_start:resource_start + len(resources)] = resources
    return bytes(output)


def compile_theme_file(ui_path: str | Path) -> bytes:
    return compile_theme_bundle(parse_theme_bundle(ui_path))
