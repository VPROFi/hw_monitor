#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys

_VENDOR = Path(__file__).resolve().parent / "smartmonitor" / "_vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from library.smartmonitor_ui import encode_ui_file

#from smartmonitor import fontfix
#fontfix.install()

with open(r'gui/hw_monitor.xml', 'rt') as f:
    xml_data = f.read()

encode_ui_file(r'gui/hw_monitor.ui', xml_data)

from library.smartmonitor_compile import compile_theme_file

compiled = compile_theme_file(r'gui/hw_monitor.ui')
with open(r'gui/hw_monitor.dat', 'wb') as f:
    f.write(compiled)