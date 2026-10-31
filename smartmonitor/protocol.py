"""Packet construction for the 3.5" SmartMonitor.

Byte layouts mirror library/lcd/lcd_comm_rev_a_hid.py from the HIDdev2 project,
so packets built here are identical on the wire to the Linux implementation.
"""

from __future__ import annotations

from datetime import datetime

REPORT_SIZE = 64
MAX_PAIRS = 20

CMD_RUNTIME = 0x02        # tag/value data update
CMD_TIME = 0x03           # set on-device clock
CMD_RESET = b"\x01reset"  # reset device
CMD_YMODEM = b"ymodem"    # enter YMODEM mode for theme upload

#: Tag numbers the stock vendor themes use. These are a *convention*, not a
#: firmware constraint -- a theme widget listens on whatever tag its
#: <fastSensor> element declares, and the device never interprets the value.
TAGS = {
    "cpu_temperature": 1,
    "cpu_frequency": 2,
    "cpu_percent": 3,
    "cpu_fan": 4,
    "gpu_temperature": 5,
    "gpu_frequency": 6,
    "gpu_percent": 7,
    "disk_total": 8,
    "gpu_memory_used": 9,
    "gpu_fan": 10,
    "gpu_memory": 11,
    "ram_load": 12,
    "ram_used": 13,
    "ram_free": 14,
    "disk_used": 15,
    "disk_free": 16,
    "disk_load": 17,
    "net_upload": 18,
    "net_download": 19,
    "ram_total": 21,
    "uptime_hours": 22,
}


def build_runtime(pairs, command: int = CMD_RUNTIME) -> bytes:
    """Build a data-update payload from (tag, value) pairs.

        payload[0]   = command
        payload[1]   = pair count
        payload[2..] = [tag: 1][value: 2 big-endian] repeating
    """
    pairs = list(pairs)
    if not 0 <= command <= 0xFF:
        raise ValueError(f"command must fit in one byte, got {command}")
    if len(pairs) > MAX_PAIRS:
        raise ValueError(
            f"at most {MAX_PAIRS} pairs fit in one packet, got {len(pairs)}")

    payload = bytearray(REPORT_SIZE)
    payload[0] = command & 0xFF
    payload[1] = len(pairs) & 0xFF

    offset = 2
    for tag, value in pairs:
        if not 0 <= tag <= 0xFF:
            raise ValueError(f"tag must fit in one byte, got {tag}")
        if not 0 <= value <= 0xFFFF:
            raise ValueError(
                f"value must fit in two bytes (0-65535), got {value}")
        payload[offset] = tag & 0xFF
        payload[offset + 1:offset + 3] = int(value).to_bytes(2, "big")
        offset += 3

    return bytes(payload)


def build_datetime(when: datetime | None = None) -> bytes:
    """Build the clock-set payload."""
    if when is None:
        when = datetime.now()
    payload = bytearray(REPORT_SIZE)
    payload[0] = CMD_TIME
    payload[1] = 0x01
    payload[2] = 0x15
    payload[3] = when.year - 2000
    payload[4] = when.month
    payload[5] = when.day
    payload[6] = when.hour
    payload[7] = when.minute
    payload[8] = when.second
    payload[9] = when.isoweekday()
    payload[10] = 0x64
    return bytes(payload)


def resolve_tag(name_or_number) -> int:
    """Accept either a tag number or a name from TAGS."""
    if isinstance(name_or_number, int):
        return name_or_number
    text = str(name_or_number).strip()
    if text.isdigit():
        return int(text)
    key = text.lower().replace("-", "_")
    if key in TAGS:
        return TAGS[key]
    raise ValueError(
        f"unknown tag {name_or_number!r}; use a number or one of: "
        + ", ".join(sorted(TAGS)))


def describe(payload: bytes) -> str:
    """Human-readable decode of a payload, for logging and debugging."""
    if not payload:
        return "(empty)"
    command = payload[0]
    if command == CMD_TIME:
        return (f"TIME 20{payload[3]:02d}-{payload[4]:02d}-{payload[5]:02d} "
                f"{payload[6]:02d}:{payload[7]:02d}:{payload[8]:02d} "
                f"(weekday {payload[9]})")
    if command == CMD_RUNTIME:
        count = payload[1]
        items = []
        for i in range(count):
            off = 2 + i * 3
            if off + 3 > len(payload):
                break
            tag = payload[off]
            value = int.from_bytes(payload[off + 1:off + 3], "big")
            items.append(f"tag {tag}={value}")
        return f"RUNTIME [{count} pairs] " + ", ".join(items)
    return f"cmd 0x{command:02X} " + payload[:16].hex(" ")
