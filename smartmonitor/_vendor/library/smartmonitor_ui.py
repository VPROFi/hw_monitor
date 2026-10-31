# SPDX-License-Identifier: GPL-3.0-or-later
#
# Utilities for working with vendor SmartMonitor theme source files (`.ui`).

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from configparser import ConfigParser
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


SMARTMONITOR_UI_KEY = b"This product is designed by OuJianbo,zhe ge chan pin shi gzbkey she ji de"
SMARTMONITOR_WIDGET_TYPE_NAMES = {
    1: "background",
    2: "static_text",
    3: "progress_bar",
    4: "image",
    5: "number",
    6: "datetime",
}


def _text(element: ET.Element | None, default: str = "") -> str:
    if element is None or element.text is None:
        return default
    return element.text.strip()


def _child_text(element: ET.Element | None, tag: str, default: str = "") -> str:
    if element is None:
        return default
    return _text(element.find(tag), default)


def _child_int(element: ET.Element | None, tag: str, default: int = 0) -> int:
    raw = _child_text(element, tag, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _hex_to_int(raw: str, default: int = 0) -> int:
    if not raw:
        return default
    raw = raw.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    try:
        return int(raw, 16)
    except ValueError:
        return default


def rc4_crypt(data: bytes, key: bytes = SMARTMONITOR_UI_KEY) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]

    i = 0
    j = 0
    out = bytearray()
    for value in data:
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out.append(value ^ s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


def decode_ui_bytes(data: bytes) -> bytes:
    return rc4_crypt(data)


def decode_ui_file(path: str | Path) -> bytes:
    return decode_ui_bytes(Path(path).read_bytes())


def encode_ui_bytes(data: bytes) -> bytes:
    return rc4_crypt(data)


def encode_ui_file(path: str | Path, xml_text: str) -> None:
    Path(path).write_bytes(encode_ui_bytes(xml_text.encode("utf-8")))


def _indent_xml(element: ET.Element, level: int = 0):
    indent = "\n" + "  " * level
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            _indent_xml(child, level + 1)
        if not element[-1].tail or not element[-1].tail.strip():
            element[-1].tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def _append_text_element(parent: ET.Element, tag: str, value: Any):
    child = ET.SubElement(parent, tag)
    child.text = "" if value is None else str(value)
    return child


def theme_to_xml(theme: "SmartMonitorTheme") -> str:
    root = ET.Element("ui")

    for parent_spec in theme.widget_parents:
        parent = ET.SubElement(
            root,
            "widgetParent",
            {
                "objectName": parent_spec.object_name,
                "type": str(parent_spec.widget_type),
            },
        )
        geometry = ET.SubElement(parent, "geometry")
        _append_text_element(geometry, "x", parent_spec.geometry.x)
        _append_text_element(geometry, "y", parent_spec.geometry.y)
        _append_text_element(geometry, "width", parent_spec.geometry.width)
        _append_text_element(geometry, "height", parent_spec.geometry.height)
        _append_text_element(parent, "backgroundType", parent_spec.background_type)
        _append_text_element(parent, "backgroundColor", parent_spec.background_color_raw)
        _append_text_element(parent, "backgroundImagePath", parent_spec.background_image_path)
        _append_text_element(parent, "imageDelay", parent_spec.image_delay)
        for key, value in parent_spec.raw_fields.items():
            if isinstance(value, dict):
                node = ET.SubElement(parent, key)
                for sub_key, sub_value in value.items():
                    _append_text_element(node, sub_key, sub_value)
            else:
                _append_text_element(parent, key, value)

    for widget_spec in theme.widgets:
        widget = ET.SubElement(
            root,
            "widget",
            {
                "globalID": str(widget_spec.global_id),
                "sameTypeID": str(widget_spec.same_type_id),
                "parentName": widget_spec.parent_name,
                "objectName": widget_spec.object_name,
                "type": str(widget_spec.widget_type),
            },
        )
        geometry = ET.SubElement(widget, "geometry")
        _append_text_element(geometry, "x", widget_spec.geometry.x)
        _append_text_element(geometry, "y", widget_spec.geometry.y)
        _append_text_element(geometry, "width", widget_spec.geometry.width)
        _append_text_element(geometry, "height", widget_spec.geometry.height)
        if widget_spec.font is not None:
            font = ET.SubElement(widget, "font")
            _append_text_element(font, "text", widget_spec.font.text)
            _append_text_element(font, "fontName", widget_spec.font.name)
            _append_text_element(font, "fontColor", widget_spec.font.color_raw)
            _append_text_element(font, "fontSize", widget_spec.font.size)
            _append_text_element(font, "bold", widget_spec.font.bold_value)
            _append_text_element(font, "italic", widget_spec.font.italic_value)
        if widget_spec.style is not None:
            style = ET.SubElement(widget, "style")
            _append_text_element(style, "showType", widget_spec.style.show_type)
            _append_text_element(style, "bgColor", widget_spec.style.bg_color_raw)
            _append_text_element(style, "fgColor", widget_spec.style.fg_color_raw)
            _append_text_element(style, "frameColor", widget_spec.style.frame_color_raw)
            _append_text_element(style, "bgImagePath", widget_spec.style.bg_image_path)
            _append_text_element(style, "fgImagePath", widget_spec.style.fg_image_path)
        if widget_spec.sensor is not None:
            sensor = ET.SubElement(widget, "sensor")
            _append_text_element(sensor, "fastSensor", widget_spec.sensor.fast_sensor)
            _append_text_element(sensor, "sensorTypeName", widget_spec.sensor.sensor_type_name)
            _append_text_element(sensor, "sensorName", widget_spec.sensor.sensor_name)
            _append_text_element(sensor, "readingName", widget_spec.sensor.reading_name)
            _append_text_element(sensor, "isDiv1204", int(widget_spec.sensor.is_div_1204))
        if widget_spec.datetime_format:
            _append_text_element(widget, "dateTimeFormat", widget_spec.datetime_format)
        for key, value in widget_spec.raw_fields.items():
            if isinstance(value, dict):
                node = ET.SubElement(widget, key)
                for sub_key, sub_value in value.items():
                    _append_text_element(node, sub_key, sub_value)
            else:
                _append_text_element(widget, key, value)

    _indent_xml(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def write_theme_file(path: str | Path, theme: "SmartMonitorTheme") -> None:
    encode_ui_file(path, theme_to_xml(theme))


@dataclass(slots=True)
class Geometry:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass(slots=True)
class FontSpec:
    text: str = ""
    name: str = ""
    color_raw: str = ""
    color: int = 0
    size: int = 0
    bold_value: int = 0
    italic_value: int = 0
    bold: bool = False
    italic: bool = False


@dataclass(slots=True)
class SensorSpec:
    fast_sensor: int = -1
    sensor_type_name: str = ""
    sensor_name: str = ""
    reading_name: str = ""
    is_div_1204: bool = False


@dataclass(slots=True)
class StyleSpec:
    show_type: int = 0
    bg_color_raw: str = ""
    bg_color: int = 0
    fg_color_raw: str = ""
    fg_color: int = 0
    frame_color_raw: str = ""
    frame_color: int = 0
    bg_image_path: str = ""
    fg_image_path: str = ""


@dataclass(slots=True)
class Widget:
    global_id: int = -1
    same_type_id: int = -1
    parent_name: str = ""
    object_name: str = ""
    widget_type: int = -1
    geometry: Geometry = field(default_factory=Geometry)
    font: FontSpec | None = None
    style: StyleSpec | None = None
    sensor: SensorSpec | None = None
    datetime_format: str = ""
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WidgetParent:
    object_name: str = ""
    widget_type: int = -1
    geometry: Geometry = field(default_factory=Geometry)
    background_type: int = 0
    background_color_raw: str = ""
    background_color: int = 0
    background_image_path: str = ""
    image_delay: int = 0
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SmartMonitorTheme:
    path: str = ""
    widget_parents: list[WidgetParent] = field(default_factory=list)
    widgets: list[Widget] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StartupPicSpec:
    path: str = ""
    total_ms: int = 0
    delay_ms: int = 0
    bg_color_raw: str = ""
    bg_color: int = 0


@dataclass(slots=True)
class SmartMonitorThemeBundle:
    ui_path: str = ""
    base_dir: str = ""
    theme: SmartMonitorTheme = field(default_factory=SmartMonitorTheme)
    startup_pic: StartupPicSpec | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def widget_type_name(widget_type: int) -> str:
    return SMARTMONITOR_WIDGET_TYPE_NAMES.get(widget_type, f"unknown_{widget_type}")


def split_argb(color: int) -> tuple[int, int]:
    return color & 0xFFFFFF, (color >> 24) & 0xFF


def qfont_record(font: FontSpec | None) -> dict[str, Any]:
    if font is None:
        return {
            "family": "",
            "size": 0,
            "bold": 0,
            "italic": 0,
        }
    return {
        "family": font.name,
        "size": font.size,
        "bold": font.bold_value,
        "italic": font.italic_value,
    }


def widget_record_fields(widget: Widget) -> list[Any]:
    if widget.widget_type == 2:
        rgb24, alpha = split_argb(widget.font.color if widget.font else 0)
        return [
            0x13,
            (widget.global_id & 0xFF) + 1,
            widget.geometry.x,
            widget.geometry.y,
            widget.geometry.width,
            widget.geometry.height,
            qfont_record(widget.font),
            rgb24,
            widget.font.text if widget.font else "",
            alpha,
        ]
    if widget.widget_type == 3:
        style = widget.style or StyleSpec()
        return [
            0x0B,
            (widget.global_id & 0xFF) + 1,
            widget.sensor.fast_sensor if widget.sensor else 0,
            widget.geometry.x,
            widget.geometry.y,
            widget.geometry.width,
            widget.geometry.height,
            style.show_type,
            style.bg_color,
            style.fg_color,
            style.frame_color,
            style.bg_image_path,
            style.fg_image_path,
        ]
    if widget.widget_type == 5:
        rgb24, alpha = split_argb(widget.font.color if widget.font else 0)
        h_align = int(widget.raw_fields.get("hAlign", 0) or 0)
        return [
            0x12,
            (widget.global_id & 0xFF) + 1,
            widget.sensor.fast_sensor if widget.sensor else 0,
            widget.geometry.x,
            widget.geometry.y,
            widget.geometry.width,
            widget.geometry.height,
            qfont_record(widget.font),
            h_align,
            rgb24,
            1 if widget.sensor and widget.sensor.is_div_1204 else 0,
            alpha,
        ]
    if widget.widget_type == 6:
        rgb24, alpha = split_argb(widget.font.color if widget.font else 0)
        h_align = int(widget.raw_fields.get("hAlign", 0) or 0)
        return [
            0x0E,
            (widget.global_id & 0xFF) + 1,
            0x15,
            widget.geometry.x,
            widget.geometry.y,
            widget.geometry.width,
            widget.geometry.height,
            qfont_record(widget.font),
            h_align,
            rgb24,
            alpha,
            widget.datetime_format.replace("\n", "\\n"),
        ]
    raise ValueError(f"Widget type {widget.widget_type} is not mapped yet")


def parse_geometry(element: ET.Element | None) -> Geometry:
    if element is None:
        return Geometry()
    return Geometry(
        x=_child_int(element, "x"),
        y=_child_int(element, "y"),
        width=_child_int(element, "width"),
        height=_child_int(element, "height"),
    )


def parse_font(element: ET.Element | None) -> FontSpec | None:
    if element is None:
        return None
    color_raw = _child_text(element, "fontColor")
    bold_value = _child_int(element, "bold")
    italic_value = _child_int(element, "italic")
    return FontSpec(
        text=_child_text(element, "text"),
        name=_child_text(element, "fontName"),
        color_raw=color_raw,
        color=_hex_to_int(color_raw),
        size=_child_int(element, "fontSize"),
        bold_value=bold_value,
        italic_value=italic_value,
        bold=bool(bold_value),
        italic=bool(italic_value),
    )


def parse_sensor(element: ET.Element | None) -> SensorSpec | None:
    if element is None:
        return None
    return SensorSpec(
        fast_sensor=_child_int(element, "fastSensor", -1),
        sensor_type_name=_child_text(element, "sensorTypeName"),
        sensor_name=_child_text(element, "sensorName"),
        reading_name=_child_text(element, "readingName"),
        is_div_1204=bool(_child_int(element, "isDiv1204")),
    )


def parse_style(element: ET.Element | None) -> StyleSpec | None:
    if element is None:
        return None
    bg_raw = _child_text(element, "bgColor")
    fg_raw = _child_text(element, "fgColor")
    frame_raw = _child_text(element, "frameColor")
    return StyleSpec(
        show_type=_child_int(element, "showType"),
        bg_color_raw=bg_raw,
        bg_color=_hex_to_int(bg_raw),
        fg_color_raw=fg_raw,
        fg_color=_hex_to_int(fg_raw),
        frame_color_raw=frame_raw,
        frame_color=_hex_to_int(frame_raw),
        bg_image_path=_child_text(element, "bgImagePath"),
        fg_image_path=_child_text(element, "fgImagePath"),
    )


def _collect_raw_fields(element: ET.Element, skip: set[str]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for child in element:
        if child.tag in skip:
            continue
        if list(child):
            raw[child.tag] = {grand.tag: _text(grand) for grand in child}
        else:
            raw[child.tag] = _text(child)
    return raw


def parse_widget_parent(element: ET.Element) -> WidgetParent:
    bg_color_raw = _child_text(element, "backgroundColor")
    return WidgetParent(
        object_name=element.attrib.get("objectName", ""),
        widget_type=int(element.attrib.get("type", "-1")),
        geometry=parse_geometry(element.find("geometry")),
        background_type=_child_int(element, "backgroundType"),
        background_color_raw=bg_color_raw,
        background_color=_hex_to_int(bg_color_raw),
        background_image_path=_child_text(element, "backgroundImagePath"),
        image_delay=_child_int(element, "imageDelay"),
        raw_fields=_collect_raw_fields(
            element,
            {"geometry", "backgroundType", "backgroundColor", "backgroundImagePath", "imageDelay"},
        ),
    )


def parse_widget(element: ET.Element) -> Widget:
    return Widget(
        global_id=int(element.attrib.get("globalID", "-1")),
        same_type_id=int(element.attrib.get("sameTypeID", "-1")),
        parent_name=element.attrib.get("parentName", ""),
        object_name=element.attrib.get("objectName", ""),
        widget_type=int(element.attrib.get("type", "-1")),
        geometry=parse_geometry(element.find("geometry")),
        font=parse_font(element.find("font")),
        style=parse_style(element.find("style")),
        sensor=parse_sensor(element.find("sensor")),
        datetime_format=_child_text(element, "dateTimeFormat"),
        raw_fields=_collect_raw_fields(
            element,
            {"geometry", "font", "style", "sensor", "dateTimeFormat"},
        ),
    )


def parse_ui_xml(xml_text: str, path: str = "") -> SmartMonitorTheme:
    root = ET.fromstring(xml_text)
    theme = SmartMonitorTheme(path=path)
    for element in root:
        if element.tag == "widgetParent":
            theme.widget_parents.append(parse_widget_parent(element))
        elif element.tag == "widget":
            theme.widgets.append(parse_widget(element))
    return theme


def parse_ui_file(path: str | Path) -> SmartMonitorTheme:
    ui_path = Path(path)
    xml_text = decode_ui_file(ui_path).decode("utf-8")
    return parse_ui_xml(xml_text, path=str(ui_path))


def resolve_theme_path(base_dir: str | Path, raw_path: str) -> Path:
    base = Path(base_dir)
    path = Path(raw_path)
    if path.is_absolute():
        return path
    if raw_path.startswith("./"):
        return base / raw_path[2:]
    return base / raw_path


def detect_frame_count(base_dir: str | Path, raw_path: str) -> int:
    path = resolve_theme_path(base_dir, raw_path)
    if not path.name:
        return 0

    stem = path.stem
    suffix = path.suffix
    digit_count = 0
    for char in reversed(stem):
        if not char.isdigit():
            break
        digit_count += 1
    if digit_count:
        prefix = stem[:-digit_count]
        count = 0
        while True:
            candidate = path.with_name(f"{prefix}{count:0{digit_count}d}{suffix}")
            if not candidate.is_file():
                break
            count += 1
        return count or 1
    return 1 if path.is_file() else 0


def parse_startup_config(config_path: str | Path) -> StartupPicSpec | None:
    config_file = Path(config_path)
    if not config_file.is_file():
        return None

    parser = ConfigParser()
    parser.read(config_file, encoding="utf-8")
    if not parser.has_section("StartupPic"):
        return None

    bg_color_raw = parser.get("StartupPic", "bgColor", fallback="")
    return StartupPicSpec(
        path=parser.get("StartupPic", "path", fallback=""),
        total_ms=parser.getint("StartupPic", "totalMs", fallback=0),
        delay_ms=parser.getint("StartupPic", "delayMs", fallback=0),
        bg_color_raw=bg_color_raw,
        bg_color=_hex_to_int(bg_color_raw),
    )


def parse_theme_bundle(ui_path: str | Path) -> SmartMonitorThemeBundle:
    ui_file = Path(ui_path)
    base_dir = ui_file.parent
    return SmartMonitorThemeBundle(
        ui_path=str(ui_file),
        base_dir=str(base_dir),
        theme=parse_ui_file(ui_file),
        startup_pic=parse_startup_config(base_dir / "config.ini"),
    )
