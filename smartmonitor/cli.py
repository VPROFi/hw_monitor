#!/usr/bin/env python3
"""SmartMonitor panel CLI -- build, preview, flash and drive 480x320 themes.

    smartmonitor list                 themes and data sources
    smartmonitor build weather        image -> .ui -> img.dat
    smartmonitor preview weather      render a PNG before flashing
    smartmonitor flash weather        write it to the panel
    smartmonitor run weather          poll the source and push values
    smartmonitor run weather --once   a single fetch and push

A theme is a directory under themes/ containing theme.json and its images.
Nothing about a theme lives in code.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

#: Themes, sources and the composio venv are looked up in the working
#: directory, so an installed `smartmonitor` command operates on the project
#: you are standing in rather than on anything inside site-packages.
PROJECT = Path.cwd()
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

THEMES_DIR = PROJECT / "themes"
VENV_PYTHON = PROJECT / ".venv-composio" / "Scripts" / "python.exe"


def _reexec_in_venv() -> None:
    """Relaunch under .venv-composio, where composio is installed.

    It is isolated there because installing it globally forces openai>=2.48,
    which breaks other packages in this environment. Everything else in this
    project is stdlib-only, so the venv runs the CLI unchanged.
    """
    if os.environ.get("_SM_REEXEC"):
        return
    python = VENV_PYTHON if VENV_PYTHON.is_file() else \
        PROJECT / ".venv-composio" / "bin" / "python"
    if not python.is_file():
        raise SystemExit(
            "This theme's source needs composio, which is not installed.\n"
            "  python -m venv .venv-composio\n"
            "  .venv-composio\\Scripts\\python -m pip install composio")
    # subprocess, not os.execv: on Windows execv flattens argv into a command
    # line, so a path containing spaces gets split apart.
    os.environ["_SM_REEXEC"] = "1"
    raise SystemExit(subprocess.run(
        [str(python), "-m", "smartmonitor.cli", *sys.argv[1:]]).returncode)


def theme_dir(name: str) -> Path:
    path = THEMES_DIR / name
    if not (path / "theme.json").is_file():
        if not THEMES_DIR.is_dir():
            raise SystemExit(
                f"no themes/ directory in {PROJECT}.\n"
                "Run this from a project that has one, or see the README "
                "for how to make a theme.")
        available = ", ".join(sorted(
            d.name for d in THEMES_DIR.iterdir()
            if (d / "theme.json").is_file())) or "(none)"
        raise SystemExit(f"no theme {name!r}. Available: {available}")
    return path


# --------------------------------------------------------------------------


def cmd_list(args) -> int:
    from sources import available
    from smartmonitor import BACKEND, find_devices
    try:
        panels = len(find_devices())
    except Exception as exc:
        panels = f"error: {str(exc)[:50]}"
    print(f"transport: {BACKEND}   panels detected: {panels}")
    print()
    print("themes:")
    for path in sorted(THEMES_DIR.iterdir()):
        spec_file = path / "theme.json"
        if not spec_file.is_file():
            continue
        from smartmonitor.themebuild import load_spec
        try:
            spec = load_spec(path)
            source = (spec.get("source") or {}).get("module", "?")
            built = "built" if (path / "img.dat").is_file() else "not built"
            print(f"  {path.name:<14} source={source:<10} "
                  f"{len(spec['fields'])} fields, {built}")
        except Exception as exc:
            print(f"  {path.name:<14} ERROR: {str(exc)[:60]}")
    print("\nsources:", ", ".join(available()))
    return 0


def cmd_build(args) -> int:
    from smartmonitor.themebuild import build
    build(theme_dir(args.theme))
    return 0

from smartmonitor.library.smartmonitor_fontfix import resolve_font_path
def cmd_preview(args) -> int:
    from PIL import Image, ImageDraw, ImageFont
    from smartmonitor.themebuild import load_spec, _colour
    from smartmonitor.library.smartmonitor_fontfix import resolve_font_path

    path = theme_dir(args.theme)
    spec = load_spec(path)
    width, height = spec["canvas"]
    scale = args.scale

    background = path / "images" / "bg.png"
    if not background.is_file():
        raise SystemExit(f"build it first: smartmonitor build {args.theme}")
    image = Image.open(background).convert("RGB").resize(
        (width * scale, height * scale), Image.NEAREST)
    draw = ImageDraw.Draw(image)

    values = {}
    for item in args.values or []:
        if "=" in item:
            key, _, val = item.partition("=")
            values[key] = val

    def paint(text, box, colour_name, size, bold):
        argb = _colour(spec, colour_name)
        rgb = (int(argb[2:4], 16), int(argb[4:6], 16), int(argb[6:8], 16))
        font_path = resolve_font_path(spec["font"], bold=bold)
        px = max(1, int(round(size * 96 / 72))) * scale
        try:
            font = ImageFont.truetype(font_path, px) if font_path else \
                ImageFont.load_default()
        except OSError:
            font = ImageFont.load_default()
        draw.text((box[0] * scale, box[1] * scale), str(text), font=font, fill=rgb)
        return draw.textbbox((box[0] * scale, box[1] * scale), str(text), font=font)

    overflow = False
    for item in spec["static"]:
        box = paint(item["text"], item["box"], item.get("color", "text"),
                    item.get("size", 12), item.get("bold", False))
        overflow |= box[2] > width * scale
    for field in spec["fields"]:
        if field.get("label"):
            paint(field["label"], field["label_box"],
                  field.get("label_color", "muted"),
                  field.get("label_size", 9), field.get("label_bold", False))
        shown = values.get(field.get("metric", ""), "0")
        box = paint(shown, field["value_box"], field.get("value_color", "text"),
                    field.get("value_size", 24), True)
        overflow |= box[2] > width * scale

    out = path / "preview.png"
    image.save(out)
    print(f"{args.theme}: {width}x{height} -> {out}")
    if overflow:
        print("WARNING: something renders past the right edge of the canvas.")
    return 0


def cmd_flash(args) -> int:
    from smartmonitor import HidError, find_devices
    from smartmonitor.ymodem import ThemeUploader

    path = theme_dir(args.theme)
    dat = path / "img.dat"
    if not dat.is_file():
        raise SystemExit(f"build it first: smartmonitor build {args.theme}")
    if not find_devices():
        raise SystemExit("No panel found. Is it plugged in?")

    data = dat.read_bytes()
    print(f"flashing {args.theme} ({len(data):,} bytes)")
    uploader = None
    try:
        uploader = ThemeUploader()
        uploader.upload(data)
    except (HidError, TimeoutError) as exc:
        print(f"\nUpload failed: {exc}", file=sys.stderr)
        print("Unplug and replug the panel, then retry.", file=sys.stderr)
        return 2
    finally:
        if uploader is not None:
            uploader.close()
    print("done")
    return 0


def cmd_run(args) -> int:
    from smartmonitor import HidError, SmartMonitorHid, build_runtime, describe
    from smartmonitor.themebuild import load_spec
    import sources

    path = theme_dir(args.theme)
    spec = load_spec(path)
    config = spec.get("source") or {}
    module = sources.load(config.get("module"))

    def once() -> int:
        snapshot = module.fetch(config)
        if hasattr(module, "describe"):
            print(f"\n{module.describe(snapshot)}")
        pairs, notes = sources.to_pairs(snapshot, spec["fields"])
        print("\n".join(notes))
        if not pairs:
            print("nothing to push")
            return 1
        payload = build_runtime(pairs)
        print(f"-> {describe(payload)}")
        if args.dry_run:
            print("(dry run: panel untouched)")
            return 0
        with SmartMonitorHid() as device:
            device.write(payload)
        print("pushed")
        return 0

    if args.once or args.dry_run:
        return once()

    print(f"polling {args.theme} every {args.interval:.0f}s. Ctrl+C to stop.")
    try:
        while True:
            try:
                once()
            except (RuntimeError, HidError) as exc:
                print(f"[warn] {exc}", file=sys.stderr)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show themes and sources")

    p = sub.add_parser("build", help="build a theme")
    p.add_argument("theme")

    p = sub.add_parser("preview", help="render a PNG")
    p.add_argument("theme")
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--values", nargs="*", metavar="metric=value")

    p = sub.add_parser("flash", help="write a theme to the panel")
    p.add_argument("theme")

    p = sub.add_parser("run", help="poll the source and push values")
    p.add_argument("theme")
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--interval", type=float, default=300.0)

    args = parser.parse_args()

    # Only the composio-backed sources need the venv; everything else runs
    # on the system interpreter.
    if args.command == "run":
        try:
            from smartmonitor.themebuild import load_spec
            spec = load_spec(theme_dir(args.theme))
            print('spec:', spec)
            if (spec.get("source") or {}).get("module") == "youtube":
                try:
                    import composio  # noqa: F401
                except ImportError:
                    _reexec_in_venv()
        except SystemExit:
            raise
        except Exception:
            pass

    handlers = {"list": cmd_list, "build": cmd_build, "preview": cmd_preview,
                "flash": cmd_flash, "run": cmd_run}
    try:
        return handlers[args.command](args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
