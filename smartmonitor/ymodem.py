"""YMODEM-over-HID theme upload.

Ported from HIDdev2's lcd_comm_rev_a_hid.py. Frame layout and command bytes are
unchanged, so this is wire-identical to the reference implementation. It runs on
whichever transport .hid selects for the platform.

Flow:
    reset -> device re-enumerates -> reopen
    "ymodem" -> ACK
    SOH block 0   : 128-byte header, "<name>\\0<size>\\0"
    STX block 1..n: 1024-byte data, padded with 0x1A
    EOT           -> ACK
    SOH block 0   : 128 zero bytes (end of batch)
"""

from __future__ import annotations

import time

from .hid import REPORT_SIZE, HidError, SmartMonitorHid, find_devices

SOH = 0x01
STX = 0x02
EOT = 0x04
ACK = 0x06
NAK = 0x15

RESET_COMMAND = b"\x01reset"
YMODEM_COMMAND = b"ymodem"

DATA_BLOCK = 1024
HEADER_BLOCK = 128
PAD = b"\x1A"


def crc16_xmodem(payload: bytes) -> int:
    crc = 0
    for byte in payload:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_frame(block_type: int, block_number: int, payload: bytes) -> bytes:
    """[type][blk][~blk][payload][crc16-be]"""
    header = bytes([block_type, block_number & 0xFF, 0xFF - (block_number & 0xFF)])
    return header + payload + crc16_xmodem(payload).to_bytes(2, "big")


def build_header_payload(remote_name: str, size: int) -> bytes:
    payload = bytearray(HEADER_BLOCK)
    header = f"{remote_name}\0{size}\0".encode("ascii")
    if len(header) > HEADER_BLOCK:
        raise ValueError(f"remote name too long: {remote_name!r}")
    payload[:len(header)] = header
    return bytes(payload)


def plan_upload(data: bytes, remote_name: str = "img.dat") -> list[bytes]:
    """Build every frame without sending, so the plan can be inspected first."""
    frames = [build_frame(SOH, 0, build_header_payload(remote_name, len(data)))]
    total = max(1, (len(data) + DATA_BLOCK - 1) // DATA_BLOCK)
    for index in range(total):
        chunk = data[index * DATA_BLOCK:(index + 1) * DATA_BLOCK].ljust(DATA_BLOCK, PAD)
        frames.append(build_frame(STX, (index + 1) & 0xFF, chunk))
    return frames


class ThemeUploader:
    def __init__(self, device: SmartMonitorHid | None = None, verbose: bool = True):
        self.device = device or SmartMonitorHid()
        self.verbose = verbose

    def _log(self, message: str):
        if self.verbose:
            print(message, flush=True)

    # -- transport helpers -------------------------------------------------

    def write_stream(self, data: bytes):
        """Send an arbitrary-length buffer as a series of 64-byte HID reports."""
        for offset in range(0, len(data), REPORT_SIZE):
            self.device.write(data[offset:offset + REPORT_SIZE])

    def expect_ack(self, timeout: float = 2.0) -> int:
        """Wait for ACK or NAK; returns the byte. Other reports are ignored."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            report = self.device.read(
                timeout_ms=max(1, int((deadline - time.monotonic()) * 1000)))
            if not report:
                continue
            if report[0] in (ACK, NAK):
                return report[0]
        raise TimeoutError("timed out waiting for ACK from the panel")

    def send_frame(self, frame: bytes, timeout: float = 2.0, retries: int = 8):
        for attempt in range(1, retries + 1):
            self.write_stream(frame)
            response = self.expect_ack(timeout=timeout)
            if response == ACK:
                return
            self._log(f"    NAK on attempt {attempt}/{retries}, resending")
        raise HidError(f"panel kept NAKing a frame after {retries} attempts")

    def reconnect(self, attempts: int = 12, delay: float = 0.5):
        """Reopen the device after it re-enumerates following a reset."""
        path = self.device.path
        try:
            self.device.close()
        except Exception:
            pass
        for attempt in range(1, attempts + 1):
            time.sleep(delay)
            if find_devices():
                try:
                    self.device = SmartMonitorHid()
                    self._log(f"    reconnected after {attempt} attempt(s)")
                    return
                except HidError:
                    continue
        raise HidError(
            f"panel did not come back after reset (was {path}). "
            "Unplug and replug it, then retry.")

    # -- upload ------------------------------------------------------------

    def upload(self, data: bytes, remote_name: str = "img.dat",
               send_reset: bool = True, ack_timeout: float = 2.0):
        if send_reset:
            self._log("  sending reset and waiting for re-enumeration...")
            try:
                self.device.write(RESET_COMMAND)
            except HidError as exc:
                self._log(f"    reset write failed ({exc}); continuing")
            time.sleep(2.5)
            self.reconnect()

        self._log("  entering YMODEM mode...")
        entered = False
        for attempt in range(1, 4):
            self.device.write(YMODEM_COMMAND)
            try:
                if self.expect_ack(timeout=2.0) == ACK:
                    entered = True
                    break
            except TimeoutError:
                self._log(f"    no ACK on attempt {attempt}/3, retrying")
                time.sleep(0.3)
        if not entered:
            raise HidError(
                "panel never acknowledged YMODEM entry. It may be held by another "
                "program (close the vendor app), or need an unplug/replug.")

        frames = plan_upload(data, remote_name)
        header, blocks = frames[0], frames[1:]

        self._log(f"  sending header ({remote_name}, {len(data):,} bytes)")
        self.send_frame(header, timeout=ack_timeout)

        self._log(f"  sending {len(blocks)} data block(s)")
        for index, frame in enumerate(blocks, start=1):
            self.send_frame(frame, timeout=ack_timeout)
            if index == 1 or index == len(blocks) or index % 8 == 0:
                self._log(f"    {index}/{len(blocks)} blocks")

        self._log("  sending EOT")
        self.device.write(bytes([EOT]))
        self.expect_ack(timeout=ack_timeout)

        self._log("  sending end-of-batch")
        self.send_frame(build_frame(SOH, 0, bytes(HEADER_BLOCK)), timeout=ack_timeout)

        self._log("  upload complete, waiting for the panel to come back")
        time.sleep(1.0)
        self.reconnect()

    def close(self):
        try:
            self.device.close()
        except Exception:
            pass
