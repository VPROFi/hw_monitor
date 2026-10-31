"""Build a SmartMonitor theme from a JSON spec.

A theme is data, not code: drop an image in, describe where the text and the
numeric fields go, and this produces the vendor .ui and the compiled img.dat.

Depends on the GPL-3.0 theme compiler from turing-smart-screen-python-HIDdev2,
so anything distributed with it is GPL-3.0 too.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

#: The vendored GPL compiler imports its own modules as `library.x`, so its
#: parent goes on sys.path rather than rewriting those files. Keeps them
#: byte-identical to upstream and makes them resolve when pip-installed.
_VENDOR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

WIDTH_DEFAULT, HEIGHT_DEFAULT = 480, 320

#: Vendor sensor metadata per tag. The panel only reads <fastSensor>; these
#: names exist so the vendor editor shows something sensible if a theme is
#: ever opened there.
TAG_SENSORS = {
    1: ("Temperature", "CPU", "CPU Package"),
    2: ("Frequency", "CPU", "Core Clock"),
    3: ("Usage", "CPU", "CPU Total"),
    5: ("Temperature", "GPU", "GPU Temperature"),
    6: ("Frequency", "GPU", "Core Clock"),
    7: ("Usage", "GPU", "GPU Load"),
    9: ("Other", "GPU", "GPU Memory Used"),
    10: ("Fan", "GPU", "GPU Fan"),
    12: ("Other", "System", "Physical Memory Load"),
    13: ("Other", "System", "Physical Memory Used"),
    17: ("Other", "Disk", "Disk Load"),
    18: ("Other", "Network:Auto", "Current UP rate"),
    19: ("Other", "Network:Auto", "Current DL rate"),
}
DEFAULT_SENSOR = ("Other", "System", "Value")


class ThemeError(RuntimeError):
    pass


def load_spec(theme_dir: Path) -> dict:
    spec_path = theme_dir / "theme.json"
    if not spec_path.is_file():
        raise ThemeError(f"no theme.json in {theme_dir}")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ThemeError(f"{spec_path.name} is not valid JSON: {exc}") from None

    spec.setdefault("canvas", [WIDTH_DEFAULT, HEIGHT_DEFAULT])
    spec.setdefault("font", "Segoe UI")
    spec.setdefault("colors", {})
    spec.setdefault("static", [])
    spec.setdefault("fields", [])
    spec["_dir"] = theme_dir

    tags = [f.get("tag") for f in spec["fields"]]
    duplicates = {t for t in tags if tags.count(t) > 1}
    if duplicates:
        raise ThemeError(
            f"tags {sorted(duplicates)} are used by more than one field; "
            "each field needs its own tag or they will overwrite each other")
    return spec


def _colour(spec: dict, name: str, default: str = "ffffffff") -> str:
    """Resolve a palette name, or accept a literal ARGB hex."""
    colours = spec.get("colors", {})
    if name in colours:
        return colours[name]
    cleaned = (name or "").lstrip("#")
    if len(cleaned) == 8:
        return cleaned
    return colours.get("text", default)


def _rgb(argb: str):
    value = int(argb, 16)
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def build_background(spec: dict, out_path: Path) -> Path:
    """Fit the source image to the canvas and dither it for RGB565.

    A background record is only emitted when backgroundImagePath is set, so a
    real image file is mandatory -- without one the panel renders uninitialised
    memory. A flat colour is produced here as an image for that reason.
    """
    from PIL import Image

    width, height = spec["canvas"]
    background = spec.get("background", {})
    source_name = background.get("image")

    if source_name:
        source = (spec["_dir"] / source_name).resolve()
        if not source.is_file():
            raise ThemeError(f"background image not found: {source}")
        image = Image.open(source).convert("RGB")
        target_aspect = width / height
        src_aspect = image.width / image.height
        if abs(src_aspect - target_aspect) > 0.01:
            if src_aspect > target_aspect:      # too wide: crop sides
                new_w = int(image.height * target_aspect)
                left = (image.width - new_w) // 2
                image = image.crop((left, 0, left + new_w, image.height))
            else:                                # too tall: crop top/bottom
                new_h = int(image.width / target_aspect)
                top = (image.height - new_h) // 2
                image = image.crop((0, top, image.width, top + new_h))
        image = image.resize((width, height), Image.LANCZOS)
    else:
        image = Image.new("RGB", (width, height),
                          _rgb(_colour(spec, "background", "ff000000")))

    amount = int(background.get("dither", 2))
    if amount > 0:
        random.seed(background.get("seed", 7))   # deterministic builds
        pixels = image.load()
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                n = random.randint(-amount, amount)
                pixels[x, y] = (min(255, max(0, r + n)),
                                min(255, max(0, g + n)),
                                min(255, max(0, b + n)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _geometry(box, indent="        ") -> str:
    x, y, w, h = box
    return (f"{indent}<geometry>\n{indent}    <x>{x}</x>\n"
            f"{indent}    <y>{y}</y>\n{indent}    <width>{w}</width>\n"
            f"{indent}    <height>{h}</height>\n{indent}</geometry>\n")


def _font_block(text, font, colour, size, bold, indent="        ") -> str:
    return (f"{indent}<font>\n"
            f"{indent}    <text>{_esc(str(text))}</text>\n"
            f"{indent}    <fontName>{_esc(font)}</fontName>\n"
            f"{indent}    <fontColor>{colour}</fontColor>\n"
            f"{indent}    <fontSize>{size}</fontSize>\n"
            f"{indent}    <bold>{1 if bold else 0}</bold>\n"
            f"{indent}    <italic>0</italic>\n{indent}</font>\n")


def _tail(indent="        ") -> str:
    return (f"{indent}<characterSet>0</characterSet>\n"
            f"{indent}<isTransparent>1</isTransparent>\n"
            f"{indent}<isAutoLineBreak>0</isAutoLineBreak>\n"
            f"{indent}<backgroundColor>ffffffff</backgroundColor>\n"
            f"{indent}<hAlign>0</hAlign>\n{indent}<vAlign>0</vAlign>\n"
            f"{indent}<isEnable>1</isEnable>\n")


def build_xml(spec: dict) -> str:
    width, height = spec["canvas"]
    font = spec["font"]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<ui>\n',
             '    <widgetParent objectName="background" type="1">\n'
             + _geometry((10, 10, width, height))
             + '        <backgroundType>1</backgroundType>\n'
               f'        <backgroundColor>{_colour(spec, "background", "ff000000")}</backgroundColor>\n'
               '        <backgroundImagePath>./images/bg.png</backgroundImagePath>\n'
               '        <imageDelay>100</imageDelay>\n'
               '    </widgetParent>\n']

    state = {"global": 0, "text": 0, "number": 0}

    def static_text(text, box, colour, size, bold):
        block = (f'    <widget objectName="StaticText {state["text"]}" '
                 f'parentName="background" globalID="{state["global"]}" '
                 f'sameTypeID="{state["text"]}" type="2">\n'
                 + _geometry(box) + "        <isHide>0</isHide>\n"
                 + _font_block(text, font, colour, size, bold) + _tail()
                 + "    </widget>\n")
        state["global"] += 1
        state["text"] += 1
        return block

    def number(tag, box, colour, size):
        type_name, sensor_name, reading = TAG_SENSORS.get(tag, DEFAULT_SENSOR)
        block = (f'    <widget objectName="Number {state["number"]}" '
                 f'parentName="background" globalID="{state["global"]}" '
                 f'sameTypeID="{state["number"]}" type="5">\n'
                 + _geometry(box) + "        <isHide>0</isHide>\n"
                 + _font_block("0", font, colour, size, True) + _tail()
                 + "        <sensor>\n"
                   f"            <fastSensor>{tag}</fastSensor>\n"
                   f"            <sensorTypeName>{_esc(type_name)}</sensorTypeName>\n"
                   f"            <sensorName>{_esc(sensor_name)}</sensorName>\n"
                   f"            <readingName>{_esc(reading)}</readingName>\n"
                   "            <isDiv1204>0</isDiv1204>\n        </sensor>\n"
                 + "    </widget>\n")
        state["global"] += 1
        state["number"] += 1
        return block

    for item in spec["static"]:
        parts.append(static_text(
            item["text"], item["box"],
            _colour(spec, item.get("color", "text")),
            item.get("size", 12), item.get("bold", False)))

    for field in spec["fields"]:
        if field.get("label"):
            parts.append(static_text(
                field["label"], field["label_box"],
                _colour(spec, field.get("label_color", "muted")),
                field.get("label_size", 9), field.get("label_bold", False)))
        parts.append(number(
            field["tag"], field["value_box"],
            _colour(spec, field.get("value_color", "text")),
            field.get("value_size", 24)))

    parts.append("</ui>\n")
    return "".join(parts)


def build(theme_dir: Path, verbose: bool = True) -> dict:
    """Build background, .ui and img.dat. Returns a summary dict."""

    spec = load_spec(theme_dir)
    xml = build_xml(spec)

    bg_path = build_background(spec, theme_dir / "images" / "bg.png")
    (theme_dir / f"{theme_dir.name}.xml").write_text(xml, encoding="utf-8")

    from library.smartmonitor_ui import encode_ui_file
    from library.smartmonitor_compile import compile_theme_file

    ui_path = theme_dir / f"{theme_dir.name}.ui"
    encode_ui_file(ui_path, xml)
    compiled = compile_theme_file(str(ui_path))
    dat_path = theme_dir / "img.dat"
    dat_path.write_bytes(compiled)

    if len(compiled) < 100_000:
        print(f"  warning: img.dat is only {len(compiled):,} bytes. A 480x320 "
              f"theme is normally ~500 KB; the background may be missing.")

    summary = {
        "name": theme_dir.name,
        "canvas": spec["canvas"],
        "background": bg_path,
        "ui": ui_path,
        "dat": dat_path,
        "size": len(compiled),
        "fields": [(f["tag"], f.get("metric"), f.get("label", ""))
                   for f in spec["fields"]],
    }
    if verbose:
        print(f"theme  : {summary['name']}  {spec['canvas'][0]}x{spec['canvas'][1]}")
        print(f"img.dat: {summary['size']:,} bytes")
        for tag, metric, label in summary["fields"]:
            print(f"  tag {tag:<3} <- {str(metric):<16} {label}")
    return summary
