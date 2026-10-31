"""Windows font resolution for the SmartMonitor theme compiler.

The upstream renderer resolves fonts by shelling out to `fc-match`, which only
exists on Linux/fontconfig systems. On Windows that call raises FileNotFoundError,
resolve_font_path() returns None, and every piece of text silently falls back to
PIL's default bitmap font -- so a compiled theme renders with wrong glyphs at the
wrong size.

This module builds a family-name index from real font files and patches the
resolver, so themes compile on Windows with the fonts they actually ask for.
"""

from __future__ import annotations

import functools
from pathlib import Path
import subprocess, sys

from PIL import ImageFont

_FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")

def default_font_dirs() -> list[Path]:
    """Font directories to index, most specific first."""
    here = Path(__file__).resolve().parent.parent
    dirs = [
        here / "vendor-app" / "fonts",          # from application
        Path(r"C:\Windows\Fonts"),
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        # For Linux/macOS:
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
    ]
    return [d for d in dirs if d.is_dir()]

def default_font_dirs_old() -> list[Path]:
    """Font directories to index, most specific first."""
    here = Path(__file__).resolve().parent.parent
    dirs = [
        here / "vendor-app" / "fonts",          # fonts shipped with the panel's app
        Path(r"C:\Windows\Fonts"),
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    ]
    return [d for d in dirs if d.is_dir()]


def _iter_font_files(dirs):
    for directory in dirs:
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in _FONT_EXTENSIONS and path.is_file():
                yield path


@functools.lru_cache(maxsize=1)
def build_index() -> dict[tuple[str, bool, bool], str]:
    """Map (family_lower, bold, italic) -> font file path.

    Earlier directories win, so the vendor's bundled fonts take precedence over
    lookalikes installed system-wide.
    """
    index: dict[tuple[str, bool, bool], str] = {}
    for path in _iter_font_files(default_font_dirs()):
        try:
            family, style = ImageFont.truetype(str(path), 12).getname()
        except Exception:
            continue
        if not family:
            continue
        style_lower = (style or "").lower()
        bold = "bold" in style_lower or "black" in style_lower or "heavy" in style_lower
        italic = "italic" in style_lower or "oblique" in style_lower
        index.setdefault((family.lower(), bold, italic), str(path))
    return index


def resolve_font_path(font_name: str, bold: bool = False, italic: bool = False):
    """Drop-in replacement for the upstream fc-match resolver."""
    index = build_index()
    family = (font_name or "").strip().lower()
    if not family:
        family = "arial"

    # Exact style, then progressively looser fallbacks.
    for key in ((family, bold, italic), (family, bold, False),
                (family, False, italic), (family, False, False)):
        if key in index:
            return index[key]

    # Still nothing: accept ANY style of the requested family before giving up
    # on it. Some families ship in a single weight only (GeForce is Bold-only),
    # and substituting a different typeface is worse than a weight mismatch.
    for (candidate_family, _, _), path in index.items():
        if candidate_family == family:
            return path

    # Family not present at all: fall back to something metric-sane rather than
    # letting the caller drop to PIL's default bitmap font.
    for fallback in ("arial", "segoe ui", "tahoma", "verdana", "dejavu sans"):
        for key in ((fallback, bold, italic), (fallback, False, False)):
            if key in index:
                return index[key]

    # For Linux/macOS use fontconfig (fc-match)
    if sys.platform != "win32":
        try:
            query = font_name or "sans-serif"
            styles: list[str] = []
            if bold: styles.append("Bold")
            if italic: styles.append("Italic")
            if styles: query = f"{query}:style={' '.join(styles)}"
            
            # Note: Ensure that the fontconfig package is installed on your system 
            # (it is usually present by default) so that the fc-match command works
            # correctly in the terminal.
            proc = subprocess.run(
                ["fc-match", "-f", "%{file}", query], 
                check=False, capture_output=True, text=True
            )
            candidate = proc.stdout.strip()
            if candidate and Path(candidate).is_file():
                return candidate
        except (FileNotFoundError, OSError):
            pass

    return None

def available_families() -> list[str]:
    """Sorted unique family names available for themes."""
    return sorted({family for family, _, _ in build_index()})
