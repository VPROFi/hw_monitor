#!/usr/bin/env python3
from smartmonitor import HidError, SmartMonitorHid, build_runtime, describe, build_datetime
import time
import pprint
import sys

SLEEP_TIME = 1

if sys.platform == "win32":
    from sources import hw_win as hw
elif sys.platform.startswith("linux"):
    from sources import hw_lin as hw

from sources import tags

TAGS = tags.TAGS

def check_value(value):
    while value >= 32768:
        print(f'ERROR: value {value} overflow')
        value = value / 1024
    return value

def get_round_item(name: str, info: dict) -> tuple:
    return (tags.TAGS[name],check_value(int(round(info[name], 0))))

def get_MB_item(name: str, info: dict) -> tuple:
    return (tags.TAGS[name],check_value(int(round((info[name]/1024)/1024, 0))))

def get_GB_item(name: str, info: dict) -> tuple:
    return (tags.TAGS[name],check_value(int(round(((info[name]/1024)/1024)/1024, 0))))

while True:

    date = build_datetime(None)
    with SmartMonitorHid() as device:
        device.write(date)
        print("pushed data")

    with SmartMonitorHid() as device:

        info = hw.fetch(None)
        pprint.pprint(info)
    
        pairs = []
        for item in ("cpu_temperature",
                     "cpu_fan",
                     "case_fan",
                     "cpu_water_pump_fan",
                     "cpu_frequency",
                     "cpu_percent",
                     "cpu_power",
                     "gpu_temperature",
                     "gpu_frequency",
                     "gpu_used_percent",
                     "memory_used_percent",
                     "gpu_memory_frequency",
                     "gpu_fan_percent",
                     "gpu_power",
                     "gpu_memory_used_percent",
                     "memory_used_percent",
                     "disk_temperature",
                     "disk_load_percent"):
            pairs.append(get_round_item(item, info))
        payload = build_runtime(pairs)

        device.write(payload)
    
        pairs = [ \
             get_MB_item("gpu_memory_used", info),
             get_MB_item("gpu_memory", info),
             get_MB_item("net_uploaded", info),
             get_MB_item("net_downloaded", info),
             get_GB_item("ram_load", info),
             get_GB_item("disk_used", info),
             get_GB_item("disk_free", info),
             ]

        payload = build_runtime(pairs)
        device.write(payload)

        print("pushed runtime")

    time.sleep(SLEEP_TIME)
