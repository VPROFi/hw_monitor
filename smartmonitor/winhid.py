"""Windows raw-HID transport for the 3.5" SmartMonitor (VID 0483, PID 0065).

Pure stdlib: talks to hid.dll / setupapi.dll / kernel32.dll through ctypes, so
there is nothing to pip install and no hidapi.dll to ship.

The upstream HIDdev2 project is Linux-only (it opens /dev/hidrawN directly).
This module is the Windows equivalent of that transport layer; the wire format
above it is identical.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

VENDOR_ID = 0x0483
PRODUCT_ID = 0x0065
REPORT_SIZE = 64  # payload bytes; writes are REPORT_SIZE + 1 (leading report id)

_DIGCF_PRESENT = 0x02
_DIGCF_DEVICEINTERFACE = 0x10
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x01
_FILE_SHARE_WRITE = 0x02
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ERROR_IO_PENDING = 997
_WAIT_TIMEOUT = 0x102

_hid = ctypes.WinDLL("hid")
_setupapi = ctypes.WinDLL("setupapi")
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_ULONG_PTR = ctypes.c_size_t


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", _ULONG_PTR),
    ]


class _HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class _HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", _ULONG_PTR),
        ("InternalHigh", _ULONG_PTR),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


_hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(_GUID)]
_hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(_HIDD_ATTRIBUTES)]
_hid.HidD_GetAttributes.restype = wintypes.BOOLEAN
_hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
_hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
_hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN
_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_HIDP_CAPS)]
_hid.HidP_GetCaps.restype = wintypes.LONG
_hid.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
_hid.HidD_SetOutputReport.restype = wintypes.BOOLEAN
_hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
_hid.HidD_GetProductString.restype = wintypes.BOOLEAN

_setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(_GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
_setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
_setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_GUID), wintypes.DWORD,
    ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA)]
_setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
_setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.WriteFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED)]
_kernel32.WriteFile.restype = wintypes.BOOL
_kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED)]
_kernel32.ReadFile.restype = wintypes.BOOL
_kernel32.GetOverlappedResult.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED),
    ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
_kernel32.GetOverlappedResult.restype = wintypes.BOOL
_kernel32.CreateEventW.argtypes = [
    ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CancelIo.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class HidError(RuntimeError):
    """Raised when the device cannot be found, opened, or written to."""


def _interface_paths():
    """Yield every present HID interface path on the system."""
    guid = _GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    dev_info = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE)
    if dev_info == _INVALID_HANDLE_VALUE:
        raise HidError("SetupDiGetClassDevs failed")
    try:
        did = _SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)
        index = 0
        while _setupapi.SetupDiEnumDeviceInterfaces(
                dev_info, None, ctypes.byref(guid), index, ctypes.byref(did)):
            index += 1
            required = wintypes.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(did), None, 0, ctypes.byref(required), None)
            if not required.value:
                continue
            buf = ctypes.create_string_buffer(required.value)
            # cbSize is 8 on 64-bit, 6 on 32-bit; the path starts at offset 4.
            ctypes.memmove(buf, ctypes.byref(
                wintypes.DWORD(8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)), 4)
            if not _setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info, ctypes.byref(did), buf, required.value,
                    ctypes.byref(required), None):
                continue
            yield ctypes.wstring_at(ctypes.addressof(buf) + 4)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(dev_info)


def _open_path(path, access, overlapped):
    flags = _FILE_FLAG_OVERLAPPED if overlapped else 0
    handle = _kernel32.CreateFileW(
        path, access, _FILE_SHARE_READ | _FILE_SHARE_WRITE, None,
        _OPEN_EXISTING, flags, None)
    if handle == _INVALID_HANDLE_VALUE:
        return None
    return handle


def find_devices(vendor_id=VENDOR_ID, product_id=PRODUCT_ID):
    """Return info dicts for every matching HID interface currently attached."""
    found = []
    for path in _interface_paths():
        # Query-only open (access 0) works even if another process holds the device.
        handle = _open_path(path, 0, overlapped=False)
        if handle is None:
            continue
        try:
            attrs = _HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(_HIDD_ATTRIBUTES)
            if not _hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                continue
            if attrs.VendorID != vendor_id or attrs.ProductID != product_id:
                continue
            info = {
                "path": path,
                "vendor_id": attrs.VendorID,
                "product_id": attrs.ProductID,
                "version": attrs.VersionNumber,
                "product": _product_string(handle),
            }
            info.update(_caps(handle))
            found.append(info)
        finally:
            _kernel32.CloseHandle(handle)
    return found


def _product_string(handle):
    buf = ctypes.create_unicode_buffer(128)
    if _hid.HidD_GetProductString(handle, buf, ctypes.sizeof(buf)):
        return buf.value
    return ""


def _caps(handle):
    preparsed = ctypes.c_void_p()
    if not _hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
        return {}
    try:
        caps = _HIDP_CAPS()
        if _hid.HidP_GetCaps(preparsed, ctypes.byref(caps)) != 0x00110000:
            return {}
        return {
            "usage_page": caps.UsagePage,
            "usage": caps.Usage,
            "input_report_len": caps.InputReportByteLength,
            "output_report_len": caps.OutputReportByteLength,
        }
    finally:
        _hid.HidD_FreePreparsedData(preparsed)


class SmartMonitorHid:
    """An open handle to the panel.

    Every write is REPORT_SIZE + 1 bytes: a leading 0x00 report-id placeholder
    (the device declares no report IDs) followed by 64 payload bytes. Writing
    any other length fails with ERROR_INVALID_PARAMETER.
    """

    def __init__(self, path=None, vendor_id=VENDOR_ID, product_id=PRODUCT_ID):
        if path is None:
            devices = find_devices(vendor_id, product_id)
            if not devices:
                raise HidError(
                    f"No HID device matching {vendor_id:04X}:{product_id:04X} is attached")
            path = devices[0]["path"]
        self.path = path
        self._handle = _open_path(
            path, _GENERIC_READ | _GENERIC_WRITE, overlapped=True)
        if self._handle is None:
            err = ctypes.get_last_error()
            raise HidError(
                f"Could not open {path} for read/write (error {err}). "
                "Another program may hold the device exclusively.")
        self._event = _kernel32.CreateEventW(None, True, False, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if getattr(self, "_handle", None) is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None
        if getattr(self, "_event", None):
            _kernel32.CloseHandle(self._event)
            self._event = None

    def write(self, payload: bytes, timeout_ms: int = 2000) -> int:
        """Send one 64-byte payload as a 65-byte HID report."""
        if len(payload) > REPORT_SIZE:
            raise ValueError(
                f"payload must fit in one report ({REPORT_SIZE} bytes, got {len(payload)})")
        report = bytes([0]) + payload.ljust(REPORT_SIZE, b"\x00")
        buf = ctypes.create_string_buffer(report, len(report))
        written = wintypes.DWORD(0)
        ov = _OVERLAPPED()
        ov.hEvent = self._event
        ok = _kernel32.WriteFile(
            self._handle, buf, len(report), ctypes.byref(written), ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != _ERROR_IO_PENDING:
                # Fall back to the control-transfer path, which some firmware
                # accepts when there is no interrupt OUT endpoint.
                if _hid.HidD_SetOutputReport(self._handle, buf, len(report)):
                    return len(report)
                raise HidError(f"WriteFile failed (error {err})")
            if _kernel32.WaitForSingleObject(self._event, timeout_ms) == _WAIT_TIMEOUT:
                _kernel32.CancelIo(self._handle)
                raise HidError(f"write timed out after {timeout_ms} ms")
            if not _kernel32.GetOverlappedResult(
                    self._handle, ctypes.byref(ov), ctypes.byref(written), False):
                raise HidError(
                    f"GetOverlappedResult failed (error {ctypes.get_last_error()})")
        return written.value

    def read(self, timeout_ms: int = 1000):
        """Read one input report, or None if the device sent nothing in time."""
        size = REPORT_SIZE + 1
        buf = ctypes.create_string_buffer(size)
        got = wintypes.DWORD(0)
        ov = _OVERLAPPED()
        ov.hEvent = self._event
        ok = _kernel32.ReadFile(
            self._handle, buf, size, ctypes.byref(got), ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != _ERROR_IO_PENDING:
                raise HidError(f"ReadFile failed (error {err})")
            if _kernel32.WaitForSingleObject(self._event, timeout_ms) == _WAIT_TIMEOUT:
                _kernel32.CancelIo(self._handle)
                return None
            if not _kernel32.GetOverlappedResult(
                    self._handle, ctypes.byref(ov), ctypes.byref(got), False):
                return None
        data = buf.raw[:got.value]
        # Unnumbered reports still arrive with the placeholder byte; drop it.
        if len(data) == size and data[0] == 0:
            data = data[1:]
        return data
