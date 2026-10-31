# SPDX-License-Identifier: GPL-3.0-or-later
#
# Experimental rendering helpers for vendor SmartMonitor payload generation.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from subprocess import run
from typing import Iterable
import math

from PIL import Image, ImageDraw, ImageFont

from library.smartmonitor_ui import FontSpec
from library.smartmonitor_font import resolve_font_path


DEFAULT_NUMBER_GLYPHS = "0123456789.-"
DEFAULT_QT_DPI = 96


@dataclass(slots=True)
class RenderedTextPayload:
    width: int
    height: int
    payload: bytes


@dataclass(slots=True)
class RenderedDatetimePayload:
    bytes_per_row: int
    height: int
    payload: bytes
    preview_widths: list[int]
    slot_advance: int


def points_to_pixels(points: int, dpi: int = DEFAULT_QT_DPI) -> int:
    return max(1, int(round(points * dpi / 72.0)))

def load_font(
    font: FontSpec | None,
    font_path: str | None = None,
    pixel_size: int | None = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font is None:
        return ImageFont.load_default()

    effective_path = font_path or resolve_font_path(font.name, bold=font.bold, italic=font.italic)
    effective_size = pixel_size or points_to_pixels(font.size)
    print(f'font.name {font.name}, effective_path {effective_path}, effective_size {effective_size}')
    if effective_path:
        try:
            return ImageFont.truetype(effective_path, effective_size)
        except OSError:
            pass
    return ImageFont.load_default()


def _render_mask(text: str, image_font: ImageFont.ImageFont) -> Image.Image:
    dummy = Image.new("L", (1, 1), 0)
    draw = ImageDraw.Draw(dummy)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=image_font)
    width = max(1, right - left)
    try:
        ascent, descent = image_font.getmetrics()
        # Vendor payloads consistently come out one pixel shorter than raw
        # PIL metrics for the closest Windows-like font match.
        height = max(1, ascent + descent - 1)
    except AttributeError:
        height = max(1, bottom - top)

    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.text((-left, 0), text, fill=255, font=image_font)
    return image

def render_vertical_text(text: str, font) -> tuple:
    dummy = Image.new("L", (1, 1), 0)
    d = ImageDraw.Draw(dummy)
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    w = int(max(1, (right - left)/len(text)))
    h = max(1, bottom - top)

    img = Image.new("L", (w, h*len(text)), 0)
    for i in range(len(text)):
       ImageDraw.Draw(img).text((-left, -top+(h*i)), text[i], fill=255, font=font)
    return img.convert("L"), w, h

def render_single_glyph(ch: str, font) -> tuple:
    dummy = Image.new("L", (1, 1), 0)
    d = ImageDraw.Draw(dummy)
    left, top, right, bottom = d.textbbox((0, 0), ch, font=font)
    w = max(1, right - left)
    h = max(1, bottom - top)

    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((-left, -top), ch, fill=255, font=font)
    return img.convert("L"), w, h

def render_datetime_text_payload(font_spec: FontSpec | None):

    DEFAULT_TIME_NUMBER_GLYPHS = "0123456789"
    SPECIAL_TIME_GLYPHS = ".-/ :PROFi "

    font = None
    if font_spec:
        path = resolve_font_path(font_spec.name, bold=font_spec.bold,
                             italic=font_spec.italic)
        if path:
            try:
                font = ImageFont.truetype(path, font_spec.size)
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    img, bmp_w, bmp_h = render_vertical_text(DEFAULT_TIME_NUMBER_GLYPHS, font)
    payload = bytearray(img.tobytes())

    glyph_widths = []

    for ch in SPECIAL_TIME_GLYPHS:
        img, w, h = render_single_glyph(ch, font)
        glyph_widths.append(w)
        zero_bytes = b'\x00'*(w*(bmp_h-h))
        payload.extend(bytes(zero_bytes))
        payload.extend(img.tobytes())

    return bmp_w, bmp_h, glyph_widths, bytes(payload)


def render_static_text_payload(
    text: str,
    font: FontSpec | None,
    font_path: str | None = None,
    pixel_size: int | None = None,
    vendor_mode: bool = False,
    binary_threshold: int | None = None,
) -> RenderedTextPayload:
    image_font = load_font(font, font_path=font_path, pixel_size=pixel_size)
    image = _render_mask(text, image_font)

    if vendor_mode and any(char.isspace() for char in text):
        dummy = Image.new("L", (1, 1), 0)
        draw = ImageDraw.Draw(dummy)
        width = max(1, int(draw.textlength(text, font=image_font)) - 1)
        image = image.crop((0, 0, min(width, image.width), image.height))

    if binary_threshold is not None:
        image = image.point(lambda value: 255 if value >= binary_threshold else 0)

    return RenderedTextPayload(
        width=image.width,
        height=image.height,
        payload=image.tobytes(),
    )


def render_number_glyph_payload(
    font: FontSpec | None,
    glyphs: str = DEFAULT_NUMBER_GLYPHS,
    font_path: str | None = None,
    pixel_size: int | None = None,
    gamma: float | None = None,
) -> tuple[list[int], int, bytes]:
    image_font = load_font(font, font_path=font_path, pixel_size=pixel_size)
    glyph_images = [_render_mask(glyph, image_font) for glyph in glyphs]
    glyph_widths = [image.width for image in glyph_images]
    glyph_height = max((image.height for image in glyph_images), default=1)

    payload = bytearray()
    for image in glyph_images:
        if image.height != glyph_height:
            padded = Image.new("L", (image.width, glyph_height), 0)
            padded.paste(image, (0, 0))
            image = padded
        if gamma is not None and gamma != 1.0:
            image = image.point(lambda value: max(0, min(255, round(((value / 255.0) ** gamma) * 255))))
        payload.extend(image.tobytes())
    return glyph_widths, glyph_height, bytes(payload)


def _pack_2bpp_row_major(image: Image.Image) -> tuple[int, bytes]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    bytes_per_row = math.ceil(width / 4)
    payload = bytearray()
    for y in range(height):
        row = [grayscale.getpixel((x, y)) for x in range(width)]
        while len(row) % 4:
            row.append(0)
        for x in range(0, len(row), 4):
            packed = 0
            for index, value in enumerate(row[x:x + 4]):
                level = min(3, max(0, int(round((value / 255.0) * 3))))
                packed |= (level & 0x3) << (6 - index * 2)
            payload.append(packed)
    return bytes_per_row, bytes(payload)


def render_datetime_preview_payload(
    preview: str,
    font: FontSpec | None,
    font_path: str | None = None,
    pixel_size: int | None = None,
) -> RenderedDatetimePayload:
    image_font = load_font(font, font_path=font_path, pixel_size=pixel_size)
    visible_preview = preview.lstrip()
    char_images = [_render_mask(char, image_font) for char in visible_preview]

    preview_widths: list[int] = []
    for char, image in zip(visible_preview, char_images):
        if char.isdigit():
            preview_widths.append(max(1, math.ceil(image.width / 2)))
        else:
            preview_widths.append(max(1, image.width))

    slot_advance = max(
        points_to_pixels(font.size if font else 16) + 1,
        max((width for width in preview_widths if width > 0), default=1),
    )

    rendered = render_static_text_payload(
        preview,
        font,
        font_path=font_path,
        pixel_size=pixel_size,
        vendor_mode=True,
        binary_threshold=160,
    )
    bbox_width = max(1, sum(preview_widths) + 8)
    canvas_width = max(4, bbox_width + 8)
    image = Image.frombytes("L", (rendered.width, rendered.height), rendered.payload)
    if image.width != bbox_width:
        image = image.resize((bbox_width, rendered.height), Image.Resampling.BILINEAR)

    canvas = Image.new("L", (canvas_width, rendered.height), 0)
    canvas.paste(image, (4, 0))
    bytes_per_row, payload = _pack_2bpp_row_major(canvas)
    return RenderedDatetimePayload(
        bytes_per_row=bytes_per_row,
        height=canvas.height,
        payload=payload,
        preview_widths=preview_widths,
        slot_advance=slot_advance,
    )


def save_payload_preview(payload: bytes, width: int, height: int, path: str | Path) -> None:
    Image.frombytes("L", (width, height), payload).save(path)


def save_number_glyph_preview(
    payload: bytes,
    glyph_widths: Iterable[int],
    glyph_height: int,
    path: str | Path,
) -> None:
    widths = [int(value) for value in glyph_widths]
    atlas = Image.new("L", (sum(widths), glyph_height), 0)
    cursor = 0
    offset = 0
    for width in widths:
        glyph_size = width * glyph_height
        glyph = Image.frombytes("L", (width, glyph_height), payload[offset:offset + glyph_size])
        atlas.paste(glyph, (cursor, 0))
        cursor += width
        offset += glyph_size
    atlas.save(path)
