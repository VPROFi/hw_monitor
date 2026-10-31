"""Windows driver for the 3.5" SmartMonitor USB HID panel (0483:0065)."""

from .protocol import (
    CMD_RUNTIME,
    CMD_TIME,
    MAX_PAIRS,
    REPORT_SIZE,
    TAGS,
    build_datetime,
    build_runtime,
    describe,
    resolve_tag,
)
from .hid import (
    BACKEND,
    PRODUCT_ID,
    VENDOR_ID,
    HidError,
    SmartMonitorHid,
    find_devices,
)

__all__ = [
    "CMD_RUNTIME", "CMD_TIME", "MAX_PAIRS", "REPORT_SIZE", "TAGS",
    "build_datetime", "build_runtime", "describe", "resolve_tag",
    "VENDOR_ID", "PRODUCT_ID", "HidError", "SmartMonitorHid", "find_devices",
    "BACKEND",
]
