#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys

_VENDOR = Path(__file__).resolve().parent / "smartmonitor" / "_vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from smartmonitor import HidError, find_devices
from smartmonitor.ymodem import ThemeUploader

with open(r'gui/hw_monitor.dat', 'rb') as f:
    data = f.read()

print(f"flashing ({len(data):,} bytes)")

uploader = None
try:
    uploader = ThemeUploader()
    uploader.upload(data)
except (HidError, TimeoutError) as exc:
    print(f"\nUpload failed: {exc}", file=sys.stderr)
    print("Unplug and replug the panel, then retry.", file=sys.stderr)
finally:
    if uploader is not None:
        uploader.close()
print("done")
