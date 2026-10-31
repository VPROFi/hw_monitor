"""Platform dispatch for the HID transport.

Everything above this layer is platform-neutral, so import the transport from
here rather than from winhid/linuxhid directly.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .winhid import (  # noqa: F401
        PRODUCT_ID, REPORT_SIZE, VENDOR_ID, HidError, SmartMonitorHid,
        find_devices,
    )
    BACKEND = "windows-ctypes"
elif sys.platform.startswith("linux"):
    from .linuxhid import (  # noqa: F401
        PRODUCT_ID, REPORT_SIZE, VENDOR_ID, HidError, SmartMonitorHid,
        find_devices,
    )
    BACKEND = "linux-hidraw"
else:
    raise ImportError(
        f"No HID transport for {sys.platform!r}. Windows (hid.dll) and Linux "
        "(hidraw) are implemented; macOS would need an IOKit backend.")

__all__ = ["PRODUCT_ID", "REPORT_SIZE", "VENDOR_ID", "HidError",
           "SmartMonitorHid", "find_devices", "BACKEND"]
