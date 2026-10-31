"""Linux hidraw transport for the 3.5" SmartMonitor (VID 0483, PID 0065).

Mirrors the public API of winhid.py, so everything above the transport --
protocol.py, ymodem.py, the CLI -- is unchanged across platforms.

Linux is the simpler side: hidraw exposes the device as a character device, so
this is os.open/os.read/os.write with no ctypes. The wire format is identical,
including the leading 0x00 report-id byte that makes every write 65 bytes.

Permissions: /dev/hidraw* is normally root-only. Install the udev rule in
tools/99-smartmonitor.rules and replug the device to use it as your own user.
"""

from __future__ import annotations

import os
import select
from pathlib import Path

VENDOR_ID = 0x0483
PRODUCT_ID = 0x0065
REPORT_SIZE = 64  # payload bytes; writes are REPORT_SIZE + 1

HIDRAW_CLASS = Path("/sys/class/hidraw")

#: hidraw's uevent spells the ids as bus:vendor:product, zero-padded to 8.
#: Bus 0003 is USB.
_HID_ID_PREFIX = "0003"


class HidError(RuntimeError):
    """Raised when the device cannot be found, opened, or written to."""


def _read_uevent(path: Path) -> dict:
    data = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                data[key.strip()] = value.strip()
    except OSError:
        pass
    return data


def find_devices(vendor_id: int = VENDOR_ID,
                 product_id: int = PRODUCT_ID) -> list[dict]:
    """Return info dicts for every matching hidraw node currently present."""
    if not HIDRAW_CLASS.is_dir():
        return []

    wanted = f"{_HID_ID_PREFIX}:{vendor_id:08X}:{product_id:08X}".upper()
    found = []
    for node in sorted(HIDRAW_CLASS.iterdir()):
        uevent = _read_uevent(node / "device" / "uevent")
        hid_id = (uevent.get("HID_ID") or "").upper()
        if hid_id != wanted:
            continue

        device_path = f"/dev/{node.name}"
        found.append({
            "path": device_path,
            "vendor_id": vendor_id,
            "product_id": product_id,
            "product": uevent.get("HID_NAME", ""),
            "uniq": uevent.get("HID_UNIQ", ""),
            "readable": os.access(device_path, os.R_OK),
            "writable": os.access(device_path, os.W_OK),
        })
    return found


def _permission_hint(path: str) -> str:
    return (f"\nCannot open {path}. hidraw nodes are root-only by default.\n"
            "Install the udev rule and replug the panel:\n"
            "  sudo cp tools/99-smartmonitor.rules /etc/udev/rules.d/\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
            "Or, to test quickly, run once with sudo.")


class SmartMonitorHid:
    """An open handle to the panel.

    Every write is REPORT_SIZE + 1 bytes: a leading 0x00 report-id placeholder
    (the device declares no report IDs) followed by 64 payload bytes.
    """

    def __init__(self, path: str | None = None, vendor_id: int = VENDOR_ID,
                 product_id: int = PRODUCT_ID):
        if path is None:
            devices = find_devices(vendor_id, product_id)
            if not devices:
                raise HidError(
                    f"No hidraw device matching {vendor_id:04X}:{product_id:04X}. "
                    "Is the panel plugged in? Check `ls /sys/class/hidraw`.")
            unusable = [d for d in devices if not (d["readable"] and d["writable"])]
            if unusable and len(unusable) == len(devices):
                raise HidError(_permission_hint(devices[0]["path"]).strip())
            path = next((d["path"] for d in devices
                         if d["readable"] and d["writable"]), devices[0]["path"])
        self.path = path
        try:
            self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise HidError(_permission_hint(path).strip()) from None
        except OSError as exc:
            raise HidError(f"could not open {path}: {exc}") from None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        fd = getattr(self, "_fd", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            self._fd = None

    def write(self, payload: bytes, timeout_ms: int = 2000) -> int:
        """Send one 64-byte payload as a 65-byte HID report."""
        if len(payload) > REPORT_SIZE:
            raise ValueError(
                f"payload must fit in one report ({REPORT_SIZE} bytes, "
                f"got {len(payload)})")
        report = bytes([0]) + payload.ljust(REPORT_SIZE, b"\x00")

        # O_NONBLOCK means a busy endpoint raises EAGAIN rather than blocking;
        # wait for writability instead of spinning.
        _, writable, _ = select.select([], [self._fd], [], timeout_ms / 1000)
        if not writable:
            raise HidError(f"write timed out after {timeout_ms} ms")
        try:
            return os.write(self._fd, report)
        except OSError as exc:
            raise HidError(f"write to {self.path} failed: {exc}") from None

    def read(self, timeout_ms: int = 1000):
        """Read one input report, or None if the device sent nothing in time."""
        readable, _, _ = select.select([self._fd], [], [], timeout_ms / 1000)
        if not readable:
            return None
        try:
            data = os.read(self._fd, REPORT_SIZE + 1)
        except BlockingIOError:
            return None
        except OSError as exc:
            raise HidError(f"read from {self.path} failed: {exc}") from None
        if not data:
            return None
        # Unnumbered reports still arrive with the placeholder byte; drop it.
        if len(data) == REPORT_SIZE + 1 and data[0] == 0:
            data = data[1:]
        return data
