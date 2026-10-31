# SPDX-License-Identifier: GPL-3.0-or-later
#
# Partial parser for compiled SmartMonitor `img.dat` files.

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


SMARTMONITOR_RECORD_SLOT_SIZE = 64

SMARTMONITOR_RECORD_TYPE_NAMES = {
    0x8B: "progress_bar_widget",
    0x8E: "datetime_widget",
    0x81: "background_image",
    0x84: "image_widget",
    0x92: "number_widget",
    0x93: "static_text_widget",
    0x94: "startup_image",
}


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _be_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "big")


def _be_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "big")


def _hi_lo_byte(high: int, low: int) -> int:
    return ((high & 0xFF) << 8) | (low & 0xFF)


def _put_be_u16(buf: bytearray, offset: int, value: int) -> None:
    buf[offset:offset + 2] = int(value & 0xFFFF).to_bytes(2, "big")


def _put_be_u32(buf: bytearray, offset: int, value: int) -> None:
    buf[offset:offset + 4] = int(value & 0xFFFFFFFF).to_bytes(4, "big")


def _put_hi_lo(buf: bytearray, offset: int, value: int) -> None:
    buf[offset] = (int(value) >> 8) & 0xFF
    buf[offset + 1] = int(value) & 0xFF


def _put_c_string(buf: bytearray, offset: int, size: int, value: str) -> None:
    raw = value.encode("ascii", errors="ignore")[:max(0, size - 1)]
    buf[offset:offset + size] = b"\x00" * size
    buf[offset:offset + len(raw)] = raw


@dataclass(slots=True)
class SmartMonitorImgDatRecord:
    index: int
    offset: int
    record_type: int
    record_type_name: str
    raw_hex: str
    fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SmartMonitorImgDat:
    path: str
    slot_count: int
    slot_size: int
    records: list[SmartMonitorImgDatRecord]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SmartMonitorImgDatResourceSpan:
    offset: int
    size: int
    record_indexes: list[int]
    record_type_names: list[str]
    source_field_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_type_name(record_type: int) -> str:
    return SMARTMONITOR_RECORD_TYPE_NAMES.get(record_type, f"unknown_0x{record_type:02x}")


def pack_record_fields(record_type: int, fields: dict[str, Any]) -> bytes:
    chunk = bytearray(SMARTMONITOR_RECORD_SLOT_SIZE)
    chunk[0] = record_type & 0xFF

    if record_type == 0x8B:
        chunk[1] = int(fields.get("widget_id", 0)) & 0xFF
        chunk[2] = int(fields.get("fast_sensor", 0)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("height", 0)))
        chunk[11] = int(fields.get("show_type", 0)) & 0xFF
        _put_be_u16(chunk, 12, int(fields.get("bg_color_rgb565", 0)))
        _put_be_u16(chunk, 14, int(fields.get("fg_color_rgb565", 0)))
        _put_be_u16(chunk, 16, int(fields.get("frame_color_rgb565", 0)))
        _put_be_u16(chunk, 18, int(fields.get("bg_image_width", 0)))
        _put_be_u16(chunk, 20, int(fields.get("bg_image_height", 0)))
        _put_be_u32(chunk, 22, int(fields.get("bg_image_offset", 0)))
        _put_be_u16(chunk, 26, int(fields.get("fg_image_width", 0)))
        _put_be_u16(chunk, 28, int(fields.get("fg_image_height", 0)))
        _put_be_u32(chunk, 30, int(fields.get("fg_image_offset", 0)))
        return bytes(chunk)

    if record_type == 0x8E:
        chunk[1] = int(fields.get("widget_id", 0)) & 0xFF
        chunk[2] = int(fields.get("time_command", 0x15)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("height", 0)))
        chunk[11] = int(fields.get("h_align", 0)) & 0xFF
        _put_be_u16(chunk, 12, int(fields.get("font_color_rgb565", 0)))
        chunk[14] = int(fields.get("font_alpha", 0)) & 0xFF
        _put_be_u32(chunk, 15, int(fields.get("glyph_bitmap_offset", 0)))
        _put_be_u16(chunk, 19, int(fields.get("glyph_bitmap_height", 0)))
        _put_be_u16(chunk, 21, int(fields.get("glyph_bitmap_width", 0)))
        glyph_widths = list(fields.get("glyph_widths", []))
        for index, value in enumerate(glyph_widths[:11]):
            _put_be_u16(chunk, 23 + index * 2, int(value))
        _put_c_string(chunk, 45, 19, str(fields.get("format_preview", "")))
        return bytes(chunk)

    if record_type == 0x84:
        chunk[1] = int(fields.get("widget_id", 0)) & 0xFF
        chunk[2] = int(fields.get("reserved_2", 0)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("height", 0)))
        _put_be_u32(chunk, 11, int(fields.get("asset_offset", 0)))
        chunk[15] = int(fields.get("frame_count", 0)) & 0xFF
        chunk[16] = 1 if fields.get("is_png", False) else 0
        _put_be_u16(chunk, 17, int(fields.get("delay_ms", 0)))
        return bytes(chunk)

    if record_type == 0x92:
        chunk[1] = int(fields.get("widget_id", 0)) & 0xFF
        chunk[2] = int(fields.get("fast_sensor", 0)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("height", 0)))
        chunk[11] = int(fields.get("h_align", 0)) & 0xFF
        _put_be_u16(chunk, 12, int(fields.get("font_color_rgb565", 0)))
        chunk[14] = 1 if fields.get("is_div_1204", False) else 0
        chunk[15] = int(fields.get("font_alpha", 0)) & 0xFF
        _put_be_u32(chunk, 16, int(fields.get("glyph_bitmap_offset", 0)))
        _put_be_u16(chunk, 20, int(fields.get("glyph_bitmap_height", 0)))
        glyph_widths = list(fields.get("glyph_widths", []))
        for index, value in enumerate(glyph_widths[:12]):
            _put_be_u16(chunk, 22 + index * 2, int(value))
        return bytes(chunk)

    if record_type == 0x93:
        chunk[1] = int(fields.get("widget_id", 0)) & 0xFF
        chunk[2] = int(fields.get("reserved_2", 0)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("rendered_width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("rendered_height", 0)))
        _put_be_u32(chunk, 11, int(fields.get("text_bitmap_offset", 0)))
        _put_be_u16(chunk, 15, int(fields.get("font_color_rgb565", 0)))
        chunk[17] = int(fields.get("font_alpha", 0)) & 0xFF
        return bytes(chunk)

    if record_type == 0x81:
        chunk[1] = int(fields.get("reserved_1", 0)) & 0xFF
        chunk[2] = int(fields.get("reserved_2", 0)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("height", 0)))
        chunk[11] = int(fields.get("background_mode_flag", 0)) & 0xFF
        _put_be_u16(chunk, 12, int(fields.get("background_color_rgb565", 0)))
        _put_be_u32(chunk, 14, int(fields.get("asset_offset", 0)))
        chunk[18] = int(fields.get("frame_count", 0)) & 0xFF
        chunk[19] = 1 if fields.get("is_png", False) else 0
        _put_be_u16(chunk, 20, int(fields.get("image_delay", 0)))
        return bytes(chunk)

    if record_type == 0x94:
        chunk[1] = int(fields.get("reserved_1", 0)) & 0xFF
        chunk[2] = int(fields.get("reserved_2", 0)) & 0xFF
        _put_hi_lo(chunk, 3, int(fields.get("x", 0)))
        _put_hi_lo(chunk, 5, int(fields.get("y", 0)))
        _put_hi_lo(chunk, 7, int(fields.get("width", 0)))
        _put_hi_lo(chunk, 9, int(fields.get("height", 0)))
        _put_be_u32(chunk, 11, int(fields.get("asset_offset", 0)))
        chunk[15] = int(fields.get("frame_count", 0)) & 0xFF
        _put_be_u16(chunk, 16, int(fields.get("total_ms", 0)))
        _put_be_u16(chunk, 18, int(fields.get("delay_ms", 0)))
        _put_be_u16(chunk, 20, int(fields.get("background_color_rgb565", 0)))
        return bytes(chunk)

    raise ValueError(f"Packing for record type 0x{record_type:02x} is not implemented")


def pack_record(record: SmartMonitorImgDatRecord) -> bytes:
    return pack_record_fields(record.record_type, record.fields)


def resource_field_name(record: SmartMonitorImgDatRecord) -> str | None:
    fields = record.fields
    for key in ("asset_offset", "glyph_bitmap_offset", "text_bitmap_offset"):
        if key in fields:
            return key
    return None


def resource_payload_size(record: SmartMonitorImgDatRecord) -> int | None:
    fields = record.fields

    if record.record_type_name == "progress_bar_widget":
        sizes = []
        for prefix in ("bg_image", "fg_image"):
            offset = int(fields.get(f"{prefix}_offset", 0))
            width = int(fields.get(f"{prefix}_width", 0))
            height = int(fields.get(f"{prefix}_height", 0))
            if offset and width and height:
                sizes.append(width * height * 2)
        return max(sizes, default=None)

    if record.record_type_name == "datetime_widget":
        return int(fields.get("glyph_bitmap_width", 0)) * int(fields.get("glyph_bitmap_height", 0))

    if record.record_type_name in {"startup_image", "background_image"}:
        width = int(fields.get("width", 0))
        height = int(fields.get("height", 0))
        frame_count = int(fields.get("frame_count", 0) or 1)
        return width * height * 2 * frame_count

    if record.record_type_name == "image_widget":
        width = int(fields.get("width", 0))
        height = int(fields.get("height", 0))
        frame_count = int(fields.get("frame_count", 0) or 1)
        bytes_per_pixel = 3 if fields.get("is_png", False) else 2
        return width * height * bytes_per_pixel * frame_count

    if record.record_type_name == "static_text_widget":
        return int(fields.get("rendered_width", 0)) * int(fields.get("rendered_height", 0))

    if record.record_type_name == "number_widget":
        glyph_widths = [int(value) for value in fields.get("glyph_widths", [])]
        glyph_height = int(fields.get("glyph_bitmap_height", 0))
        return sum(glyph_widths) * glyph_height

    return None


def collect_resource_spans(parsed: SmartMonitorImgDat) -> list[SmartMonitorImgDatResourceSpan]:
    grouped: dict[int, SmartMonitorImgDatResourceSpan] = {}

    for record in parsed.records:
        field_name = resource_field_name(record)
        if field_name is None:
            continue
        offset = int(record.fields[field_name])
        size = resource_payload_size(record)
        if size is None:
            continue

        span = grouped.get(offset)
        if span is None:
            span = SmartMonitorImgDatResourceSpan(
                offset=offset,
                size=size,
                record_indexes=[record.index],
                record_type_names=[record.record_type_name],
                source_field_names=[field_name],
            )
            grouped[offset] = span
        else:
            span.size = max(span.size, size)
            span.record_indexes.append(record.index)
            span.record_type_names.append(record.record_type_name)
            span.source_field_names.append(field_name)

    return sorted(grouped.values(), key=lambda item: item.offset)


def rebuild_imgdat(
    original_data: bytes,
    parsed: SmartMonitorImgDat,
) -> bytes:
    resource_spans = collect_resource_spans(parsed)
    output_size = max(
        len(original_data),
        max((span.offset + span.size for span in resource_spans), default=0),
        (parsed.slot_count + 1) * SMARTMONITOR_RECORD_SLOT_SIZE,
    )
    rebuilt = bytearray(output_size)
    rebuilt[:len(original_data)] = original_data

    rebuilt[0:4] = int(parsed.slot_count).to_bytes(4, "little")

    for record in parsed.records:
        start = record.offset
        end = start + SMARTMONITOR_RECORD_SLOT_SIZE
        raw = original_data[start:end]
        if record.record_type_name.startswith("unknown_"):
            rebuilt[start:end] = raw
        else:
            rebuilt[start:end] = pack_record(record)

    for span in resource_spans:
        rebuilt[span.offset:span.offset + span.size] = original_data[span.offset:span.offset + span.size]

    return bytes(rebuilt)


def parse_record(index: int, chunk: bytes) -> SmartMonitorImgDatRecord:
    record_type = chunk[0]
    fields: dict[str, Any] = {}

    if record_type == 0x84:
        fields = {
            "widget_id": chunk[1],
            "reserved_2": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "width": _hi_lo_byte(chunk[7], chunk[8]),
            "height": _hi_lo_byte(chunk[9], chunk[10]),
            "asset_offset": _be_u32(chunk, 11),
            "frame_count": chunk[15],
            "is_png": bool(chunk[16]),
            "delay_ms": _be_u16(chunk, 17),
        }
    elif record_type == 0x8B:
        fields = {
            "widget_id": chunk[1],
            "fast_sensor": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "width": _hi_lo_byte(chunk[7], chunk[8]),
            "height": _hi_lo_byte(chunk[9], chunk[10]),
            "show_type": chunk[11],
            "bg_color_rgb565": _be_u16(chunk, 12),
            "fg_color_rgb565": _be_u16(chunk, 14),
            "frame_color_rgb565": _be_u16(chunk, 16),
            "bg_image_width": _be_u16(chunk, 18),
            "bg_image_height": _be_u16(chunk, 20),
            "bg_image_offset": _be_u32(chunk, 22),
            "fg_image_width": _be_u16(chunk, 26),
            "fg_image_height": _be_u16(chunk, 28),
            "fg_image_offset": _be_u32(chunk, 30),
        }
    elif record_type == 0x8E:
        raw_preview = chunk[45:64].split(b"\x00", 1)[0]
        fields = {
            "widget_id": chunk[1],
            "time_command": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "width": _hi_lo_byte(chunk[7], chunk[8]),
            "height": _hi_lo_byte(chunk[9], chunk[10]),
            "h_align": chunk[11],
            "font_color_rgb565": _be_u16(chunk, 12),
            "font_alpha": chunk[14],
            "glyph_bitmap_offset": _be_u32(chunk, 15),
            "glyph_bitmap_height": _be_u16(chunk, 19),
            "glyph_bitmap_width": _be_u16(chunk, 21),
            "glyph_widths": [_be_u16(chunk, offset) for offset in range(23, 45, 2)],
            "format_preview": raw_preview.decode("ascii", errors="ignore"),
        }
    elif record_type == 0x92:
        fields = {
            "widget_id": chunk[1],
            "fast_sensor": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "width": _hi_lo_byte(chunk[7], chunk[8]),
            "height": _hi_lo_byte(chunk[9], chunk[10]),
            "h_align": chunk[11],
            "font_color_rgb565": _be_u16(chunk, 12),
            "is_div_1204": bool(chunk[14]),
            "font_alpha": chunk[15],
            "glyph_bitmap_offset": _be_u32(chunk, 16),
            "glyph_bitmap_height": _be_u16(chunk, 20),
            "glyph_widths": [_be_u16(chunk, offset) for offset in range(22, 46, 2)],
        }
    elif record_type == 0x93:
        fields = {
            "widget_id": chunk[1],
            "reserved_2": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "rendered_width": _hi_lo_byte(chunk[7], chunk[8]),
            "rendered_height": _hi_lo_byte(chunk[9], chunk[10]),
            "text_bitmap_offset": _be_u32(chunk, 11),
            "font_color_rgb565": _be_u16(chunk, 15),
            "font_alpha": chunk[17],
        }
    elif record_type == 0x81:
        fields = {
            "reserved_1": chunk[1],
            "reserved_2": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "width": _hi_lo_byte(chunk[7], chunk[8]),
            "height": _hi_lo_byte(chunk[9], chunk[10]),
            "background_mode_flag": chunk[11],
            "background_color_rgb565": _be_u16(chunk, 12),
            "asset_offset": _be_u32(chunk, 14),
            "frame_count": chunk[18],
            "is_png": bool(chunk[19]),
            "image_delay": _be_u16(chunk, 20),
        }
    elif record_type == 0x94:
        fields = {
            "reserved_1": chunk[1],
            "reserved_2": chunk[2],
            "x": _hi_lo_byte(chunk[3], chunk[4]),
            "y": _hi_lo_byte(chunk[5], chunk[6]),
            "width": _hi_lo_byte(chunk[7], chunk[8]),
            "height": _hi_lo_byte(chunk[9], chunk[10]),
            "asset_offset": _be_u32(chunk, 11),
            "frame_count": chunk[15],
            "total_ms": _be_u16(chunk, 16),
            "delay_ms": _be_u16(chunk, 18),
            "background_color_rgb565": _be_u16(chunk, 20),
        }
    else:
        fields = {
            "bytes_u16": [_u16(chunk, offset) for offset in range(0, len(chunk), 2)],
        }

    return SmartMonitorImgDatRecord(
        index=index,
        offset=index * SMARTMONITOR_RECORD_SLOT_SIZE,
        record_type=record_type,
        record_type_name=record_type_name(record_type),
        raw_hex=chunk.hex(),
        fields=fields,
    )


def parse_imgdat(data: bytes, path: str = "") -> SmartMonitorImgDat:
    slot_count = _u32(data, 0)
    records: list[SmartMonitorImgDatRecord] = []
    for index in range(1, slot_count + 1):
        offset = index * SMARTMONITOR_RECORD_SLOT_SIZE
        chunk = data[offset:offset + SMARTMONITOR_RECORD_SLOT_SIZE]
        if len(chunk) < SMARTMONITOR_RECORD_SLOT_SIZE:
            break
        if not any(chunk):
            continue
        records.append(parse_record(index, chunk))
    return SmartMonitorImgDat(
        path=path,
        slot_count=slot_count,
        slot_size=SMARTMONITOR_RECORD_SLOT_SIZE,
        records=records,
    )


def parse_imgdat_file(path: str | Path) -> SmartMonitorImgDat:
    imgdat_path = Path(path)
    return parse_imgdat(imgdat_path.read_bytes(), path=str(imgdat_path))
