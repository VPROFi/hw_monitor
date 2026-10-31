#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys

_VENDOR = Path(__file__).resolve().parent / "smartmonitor" / "_vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from library.smartmonitor_ui import decode_ui_file

with open(r'gui/hw_monitor.xml', 'wb') as f:
    f.write(decode_ui_file(r'gui/hw_monitor.ui'))