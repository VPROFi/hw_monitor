import re
import requests
try:
    from .get_disk_usage import get_all_disks_usage
    from .tags import TAGS
except:
    from get_disk_usage import get_all_disks_usage
    from tags import TAGS

LHM_URL = "http://127.0.0.1:8085/data.json"


def to_float(value):
    """
    Преобразует значение из JSON в float.
    Сначала пытается использовать RawValue, но если его нет,
    парсит строки вида "3,5 W", "4303,1 MHz".
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    # Примеры значений: "3,5 W", "4303,1 MHz", "286,000".
    # Берём часть до первого пробела и заменяем запятую на точку.
    text = text.split()[0].replace("\xa0", "").replace(",", ".")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def natural_key(text):
    """
    Естественная сортировка строк:
    Core #2 будет раньше Core #10.
    """
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text or "")
    ]


def iter_sensors(node, hardware_text=None, hardware_id=None, hardware_type=None):
    """
    Рекурсивно обходит JSON от LibreHardwareMonitor/OpenHardwareMonitor.
    Возвращает сенсоры:
    - hardware: имя железного блока
    - hardware_id: HardwareId
    - hardware_type: HardwareType, если есть
    - sensor: имя сенсора
    - type: Temperature, Fan, Clock, Power и т.д.
    - identifier: SensorId
    - value: числовое значение
    """
    if isinstance(node, dict):
        next_text = hardware_text
        next_id = hardware_id
        next_type = hardware_type

        node_hardware_id = node.get("HardwareId")
        node_hardware_type = node.get("HardwareType")

        # Если это узел оборудования, запоминаем его имя и идентификатор.
        if node_hardware_id is not None or node_hardware_type is not None:
            next_text = node.get("Text") or hardware_text
            if node_hardware_id is not None:
                next_id = node_hardware_id
            if node_hardware_type is not None:
                next_type = node_hardware_type

        # LibreHardwareMonitor использует Type / SensorId.
        # Старый OpenHardwareMonitor мог использовать SensorType / Identifier.
        sensor_type = node.get("SensorType") or node.get("Type")
        identifier = node.get("Identifier") or node.get("SensorId")

        if sensor_type is not None and identifier is not None:
            value = to_float(node.get("RawValue"))

            if value is None:
                value = to_float(node.get("Value"))

            yield {
                "hardware": hardware_text,
                "hardware_id": hardware_id,
                "hardware_type": hardware_type,
                "sensor": node.get("Text"),
                "type": sensor_type,
                "identifier": identifier,
                "value": value,
            }

        children = node.get("Children")

        # На случай старого/альтернативного формата, где корень может быть {"value": [...]}.
        if children is None and isinstance(node.get("value"), list):
            children = node.get("value")

        for child in children or []:
            yield from iter_sensors(child, next_text, next_id, next_type)

    elif isinstance(node, list):
        for item in node:
            yield from iter_sensors(item, hardware_text, hardware_id, hardware_type)

def get_system_metrics(data, gpu_hadware_id = None, pump_identifier_id = None):
    """
    Преобразует JSON LibreHardwareMonitor в словарь параметров.
    Если параметр не найден, возвращает 0.
    """
    METRIC_KEYS = tuple(TAGS.keys())

    result = {key: 0 for key in METRIC_KEYS}

    try:
        sensors = list(iter_sensors(data))
    except Exception:
        sensors = []

    def sensor_name(s):
        return (s.get("sensor") or "").lower()

    def hardware_name(s):
        return (s.get("hardware") or "").lower()

    def hardware_id(s):
        return s.get("hardware_id") or ""

    def identifier(s):
        return s.get("identifier") or ""

    def raw_value(s):
        if not s:
            return None

        v = s.get("value")
        if v is None:
            return None

        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def value_of(s):
        v = raw_value(s)
        return 0.0 if v is None else v

    def first_by_name(items, keywords):
        """
        Ищет первый сенсор, в имени которого есть одно из слов.
        Порядок слов в keywords важен.
        """
        for kw in keywords:
            for item in items:
                if kw in sensor_name(item):
                    return item
        return None

    def is_cpu(s):
        if (s.get("hardware_type") or "").lower() == "cpu":
            return True

        hid = hardware_id(s)
        iid = identifier(s)

        if hid.startswith(("/intelcpu", "/amdcpu")):
            return True

        if iid.startswith(("/intelcpu", "/amdcpu")):
            return True

        hw = hardware_name(s)
        return "cpu" in hw and "gpu" not in hw

    def is_gpu(s, gpu_hadware_id):
        if (s.get("hardware_type") or "").lower() == "gpu":
            return True

        hid = hardware_id(s)
        iid = identifier(s)

        if gpu_hadware_id not in (None, ""):
            if hid != gpu_hadware_id:
                return False
            else:
                return True

        if hid.startswith("/gpu"):
            return True

        if iid.startswith("/gpu"):
            return True

        hw = hardware_name(s)

        return (
            "gpu" in hw
            or "graphics" in hw
            or "nvidia" in hw
            or "geforce" in hw
            or "radeon" in hw
        ) and "cpu" not in hw

    def is_disk(s):
        hid = hardware_id(s)

        if hid.startswith(
            (
                "/ahci",
                "/nvme",
                "/ata",
                "/scsi",
                "/hdd",
                "/storage",
                "/usbhdd",
                "/usbstorage",
            )
        ):
            return True

        hw = hardware_name(s)

        return (
            "ssd" in hw
            or "hdd" in hw
            or "disk" in hw
        ) and "memory" not in hw

    def is_nic(s):
        if hardware_id(s).startswith("/nic"):
            return True

        hw = hardware_name(s)

        return (
            "ethernet" in hw
            or "wi-fi" in hw
            or "wireless" in hw
            or "network" in hw
            or "realtek" in hw
        )

    def is_virtual_nic(s):
        hw = hardware_name(s)

        virtual_markers = (
            "vmware",
            "virtual",
            "virtualbox",
            "hyper-v",
            "loopback",
            "teredo",
            "isatap",
            "vpn",
            "hamachi",
            "zerotier",
            "tailscale",
        )

        return any(marker in hw for marker in virtual_markers)

    # =====================
    # CPU
    # =====================

    cpu_temperatures = [
        s for s in sensors
        if s.get("type") == "Temperature"
        and s.get("value") is not None
        and is_cpu(s)
    ]

    cpu_temp_sensor = first_by_name(
        cpu_temperatures,
        [
            "cpu package",
            "package",
            "core average",
            "core max",
            "cpu core",
        ]
    )

    if cpu_temp_sensor:
        result["cpu_temperature"] = value_of(cpu_temp_sensor)
    elif cpu_temperatures:
        result["cpu_temperature"] = max(value_of(s) for s in cpu_temperatures)

    cpu_clocks = [
        s for s in sensors
        if s.get("type") == "Clock"
        and s.get("value") is not None
        and is_cpu(s)
    ]

    core_clocks = [
        s for s in cpu_clocks
        if sensor_name(s).startswith("cpu core")
    ]

    if core_clocks:
        # Средняя частота по ядрам.
        # Если нужна максимальная частота, замените sum/len на max(...).
        result["cpu_frequency"] = sum(value_of(s) for s in core_clocks) / len(core_clocks)
    else:
        usable_clocks = [
            s for s in cpu_clocks
            if "bus" not in sensor_name(s)
        ]

        if usable_clocks:
            result["cpu_frequency"] = sum(value_of(s) for s in usable_clocks) / len(usable_clocks)

    cpu_loads = [
        s for s in sensors
        if s.get("type") == "Load"
        and s.get("value") is not None
        and is_cpu(s)
    ]

    cpu_load_sensor = first_by_name(
        cpu_loads,
        [
            "cpu total",
            "total",
            "core max",
        ]
    )

    if cpu_load_sensor:
        result["cpu_percent"] = value_of(cpu_load_sensor)
    else:
        thread_loads = [
            s for s in cpu_loads
            if "thread" in sensor_name(s)
        ]

        core_loads = [
            s for s in cpu_loads
            if sensor_name(s).startswith("cpu core")
        ]

        if thread_loads:
            result["cpu_percent"] = sum(value_of(s) for s in thread_loads) / len(thread_loads)
        elif core_loads:
            result["cpu_percent"] = sum(value_of(s) for s in core_loads) / len(core_loads)
        elif cpu_loads:
            result["cpu_percent"] = max(value_of(s) for s in cpu_loads)

    cpu_powers = [
        s for s in sensors
        if s.get("type") == "Power"
        and s.get("value") is not None
        and is_cpu(s)
    ]

    cpu_power_sensor = first_by_name(
        cpu_powers,
        [
            "cpu package",
            "package",
            "cpu cores",
            "cores",
            "cpu",
        ]
    )

    if cpu_power_sensor:
        result["cpu_power"] = value_of(cpu_power_sensor)
    elif cpu_powers:
        result["cpu_power"] = value_of(cpu_powers[0])

    # =====================
    # Вентиляторы
    # =====================

    fans = [
        s for s in sensors
        if s.get("type") == "Fan"
        and s.get("value") is not None
    ]

    pump_keywords = ("water", "pump", "aio", "liquid")
    cpu_fan_keywords = ("cpu", "proc")
    case_fan_keywords = (
        "chassis",
        "case",
        "system",
        "sys",
        "rear",
        "front",
        "top",
        "aux",
    )

    if pump_identifier_id is not None:
        pump_fans = [
            s for s in fans
            if identifier(s) == pump_identifier_id
        ]
    else:
        pump_fans = [
            s for s in fans
            if any(k in sensor_name(s) for k in pump_keywords)
        ]

    pump_ids = {id(s) for s in pump_fans}

    explicit_cpu_fans = [
        s for s in fans
        if id(s) not in pump_ids
        and any(k in sensor_name(s) for k in cpu_fan_keywords)
    ]

    cpu_fan_ids = {id(s) for s in explicit_cpu_fans}

    explicit_case_fans = [
        s for s in fans
        if id(s) not in pump_ids
        and id(s) not in cpu_fan_ids
        and any(k in sensor_name(s) for k in case_fan_keywords)
    ]

    case_fan_ids = {id(s) for s in explicit_case_fans}

    other_fans = [
        s for s in fans
        if id(s) not in pump_ids
        and id(s) not in cpu_fan_ids
        and id(s) not in case_fan_ids
    ]

    if pump_fans:
        result["cpu_water_pump_fan"] = value_of(pump_fans[0])

    if explicit_cpu_fans:
        cpu_fan_sensor = explicit_cpu_fans[0]
    elif other_fans:
        # Если имени CPU Fan нет, часто первый вентилятор — это CPU-вентилятор.
        cpu_fan_sensor = other_fans[0]
    else:
        cpu_fan_sensor = None

    result["cpu_fan"] = value_of(cpu_fan_sensor)

    if explicit_case_fans:
        case_fan_sensor = explicit_case_fans[0]
    else:
        remaining_other_fans = [
            s for s in other_fans
            if s is not cpu_fan_sensor
        ]

        case_fan_sensor = remaining_other_fans[0] if remaining_other_fans else None

    result["case_fan"] = value_of(case_fan_sensor)

    # =====================
    # GPU
    # =====================

    gpu_temperatures = [
        s for s in sensors
        if s.get("type") == "Temperature"
        and s.get("value") is not None
        and is_gpu(s, gpu_hadware_id)
    ]

    gpu_temp_sensor = first_by_name(
        gpu_temperatures,
        [
            "gpu package",
            "gpu core",
            "gpu",
            "core",
        ]
    )

    if gpu_temp_sensor:
        if gpu_hadware_id is None and hardware_id(gpu_temp_sensor) != "":
            gpu_hadware_id = hardware_id(gpu_temp_sensor)
            print(f'Use: gpu_hadware_id {gpu_hadware_id}')
        result["gpu_temperature"] = value_of(gpu_temp_sensor)
    elif gpu_temperatures:
        result["gpu_temperature"] = max(value_of(s) for s in gpu_temperatures)

    gpu_clocks = [
        s for s in sensors
        if s.get("type") == "Clock"
        and s.get("value") is not None
        and is_gpu(s, gpu_hadware_id)
    ]

    gpu_core_clock = first_by_name(
        gpu_clocks,
        [
            "gpu core",
            "core",
        ]
    )

    if gpu_core_clock:
        result["gpu_frequency"] = value_of(gpu_core_clock)
    else:
        non_memory_clocks = [
            s for s in gpu_clocks
            if "memory" not in sensor_name(s)
        ]

        if non_memory_clocks:
            result["gpu_frequency"] = value_of(non_memory_clocks[0])

    gpu_memory_clock = first_by_name(
        gpu_clocks,
        [
            "gpu memory",
            "memory",
        ]
    )

    result["gpu_memory_frequency"] = value_of(gpu_memory_clock)

    gpu_loads = [
        s for s in sensors
        if s.get("type") == "Load"
        and s.get("value") is not None
        and is_gpu(s, gpu_hadware_id)
    ]

    gpu_used_sensor = first_by_name(
        gpu_loads,
        [
            "gpu core",
            "d3d 3d",
            "core",
            "utilization",
            "usage",
        ]
    )

    if gpu_used_sensor:
        result["gpu_used_percent"] = value_of(gpu_used_sensor)
    elif gpu_loads:
        result["gpu_used_percent"] = max(value_of(s) for s in gpu_loads)

    gpu_data = [
        s for s in sensors
        if s.get("type") == "Data"
        and s.get("value") is not None
        and is_gpu(s, gpu_hadware_id)
    ]

    gpu_memory_total_sensor = first_by_name(
        gpu_data,
        [
            "gpu memory total",
            "shared memory total",
            "memory total",
            "total memory",
            "total",
        ]
    )

    gpu_memory_used_sensor = first_by_name(
        gpu_data,
        [
            "gpu memory used",
            "shared memory used",
            "memory used",
            "used",
        ]
    )

    gpu_memory_free_sensor = first_by_name(
        gpu_data,
        [
            "gpu memory free",
            "shared memory free",
            "memory free",
            "free",
            "available",
        ]
    )

    gpu_total = raw_value(gpu_memory_total_sensor)
    gpu_used = raw_value(gpu_memory_used_sensor)
    gpu_free = raw_value(gpu_memory_free_sensor)

    # Если нет отдельного Total, но есть Used и Free — считаем Total.
    if gpu_total is None and gpu_used is not None and gpu_free is not None:
        gpu_total = gpu_used + gpu_free

    # Если нет Used, но есть Total и Free — считаем Used.
    if gpu_used is None and gpu_total is not None and gpu_free is not None:
        gpu_used = gpu_total - gpu_free

    # Общая память GPU в байтах.
    if gpu_total is not None:
        result["gpu_memory"] = gpu_total

    # Использованная память GPU в байтах.
    if gpu_used is not None:
        result["gpu_memory_used"] = max(gpu_used, 0.0)
    else:
        result["gpu_memory_used"] = 0

    gpu_memory_load_sensor = first_by_name(
        [
            s for s in gpu_loads
            if "memory" in sensor_name(s)
        ],
        [
            "memory used",
            "memory",
        ]
    )

    if gpu_memory_load_sensor:
        result["gpu_memory_used_percent"] = value_of(gpu_memory_load_sensor)
    else:
        if gpu_used is None and gpu_total is not None and gpu_free is not None:
            gpu_used = gpu_total - gpu_free

        if gpu_used is not None and gpu_total:
            if gpu_total > 0:
                result["gpu_memory_used_percent"] = gpu_used / gpu_total * 100

    gpu_controls = [
        s for s in sensors
        if s.get("type") == "Control"
        and s.get("value") is not None
        and is_gpu(s, gpu_hadware_id)
    ]

    gpu_fan_control = first_by_name(
        gpu_controls,
        [
            "gpu fan",
            "fan",
        ]
    )

    if gpu_fan_control:
        result["gpu_fan_percent"] = value_of(gpu_fan_control)
    elif gpu_controls:
        result["gpu_fan_percent"] = value_of(gpu_controls[0])
    else:
        gpu_fan_load = first_by_name(
            [
                s for s in gpu_loads
                if "fan" in sensor_name(s)
            ],
            [
                "fan",
            ]
        )

        result["gpu_fan_percent"] = value_of(gpu_fan_load)

    gpu_powers = [
        s for s in sensors
        if s.get("type") == "Power"
        and s.get("value") is not None
        and is_gpu(s, gpu_hadware_id)
    ]

    gpu_power_sensor = first_by_name(
        gpu_powers,
        [
            "gpu package",
            "gpu power",
            "gpu core",
            "power",
        ]
    )

    if gpu_power_sensor:
        result["gpu_power"] = value_of(gpu_power_sensor)
    elif gpu_powers:
        result["gpu_power"] = value_of(gpu_powers[0])

    # =====================
    # Сеть
    # =====================

    nic_data = [
        s for s in sensors
        if s.get("type") == "Data"
        and s.get("value") is not None
        and is_nic(s)
    ]

    physical_nic_data = [
        s for s in nic_data
        if not is_virtual_nic(s)
    ]

    selected_nic_data = physical_nic_data or nic_data

    upload_keywords = (
        "uploaded",
        "upload",
        "sent",
        "tx",
    )

    download_keywords = (
        "downloaded",
        "download",
        "received",
        "rx",
    )

    result["net_uploaded"] = sum(
        value_of(s) for s in selected_nic_data
        if any(k in sensor_name(s) for k in upload_keywords)
    )

    result["net_downloaded"] = sum(
        value_of(s) for s in selected_nic_data
        if any(k in sensor_name(s) for k in download_keywords)
    )

    # =====================
    # RAM / память
    # =====================

    def is_ram(s):
        return hardware_id(s) == "/ram" or "total memory" in hardware_name(s)

    ram_data = [
        s for s in sensors
        if s.get("type") == "Data"
        and s.get("value") is not None
        and is_ram(s)
    ]

    ram_loads = [
        s for s in sensors
        if s.get("type") == "Load"
        and s.get("value") is not None
        and is_ram(s)
    ]

    memory_used_sensor = first_by_name(
        ram_data,
        [
            "memory used",
            "used",
        ]
    )

    ram_free_sensor = first_by_name(
        ram_data,
        [
            "memory available",
            "memory free",
            "free",
            "available",
        ]
    )

    ram_total_sensor = first_by_name(
        ram_data,
        [
            "memory total",
            "total",
        ]
    )

    result["ram_load"] = value_of(memory_used_sensor)
    result["ram_free"] = value_of(ram_free_sensor)

    if ram_total_sensor:
        result["ram_total"] = value_of(ram_total_sensor)
    elif memory_used_sensor and ram_free_sensor:
        result["ram_total"] = value_of(memory_used_sensor) + value_of(ram_free_sensor)

    ram_load_sensor = first_by_name(
        ram_loads,
        [
            "memory",
            "load",
        ]
    )

    result["memory_used_percent"] = value_of(ram_load_sensor)

    # =====================
    # Диски
    # =====================

    disk_sensors = [
        s for s in sensors
        if is_disk(s)
    ]

    disk_temperatures = [
        s for s in disk_sensors
        if s.get("type") == "Temperature"
        and s.get("value") is not None
    ]

    if len(disk_temperatures):
        result["disk_temperature"] = value_of(disk_temperatures[0])

    result["disk_used"], result["disk_free"] = get_all_disks_usage()

    if result["disk_used"]:
        result["disk_load_percent"] = (result["disk_used"]/(result["disk_used"]+result["disk_free"]))*100


    '''disk_data = [
        s for s in disk_sensors
        if s.get("type") == "Data"
        and s.get("value") is not None
    ]

    disk_hw_ids = []

    for s in disk_sensors:
        hid = hardware_id(s)

        if hid and hid not in disk_hw_ids:
            disk_hw_ids.append(hid)

    total_disk_used = 0.0
    total_disk_free = 0.0

    for hid in disk_hw_ids:
        current_disk_data = [
            s for s in disk_data
            if hardware_id(s) == hid
        ]

        total_space_sensor = first_by_name(
            current_disk_data,
            [
                "total space",
                "total",
                "capacity",
            ]
        )

        free_space_sensor = first_by_name(
            current_disk_data,
            [
                "free space",
                "free",
                "available",
            ]
        )

        used_space_sensor = first_by_name(
            current_disk_data,
            [
                "used space",
                "used",
            ]
        )

        total_space = raw_value(total_space_sensor)
        free_space = raw_value(free_space_sensor)
        used_space = raw_value(used_space_sensor)

        if total_space is not None and free_space is not None:
            total_disk_free += max(free_space, 0.0)
            total_disk_used += max(total_space - free_space, 0.0)
        elif used_space is not None:
            total_disk_used += max(used_space, 0.0)

            if free_space is not None:
                total_disk_free += max(free_space, 0.0)

    result["disk_used"] = total_disk_used
    result["disk_free"] = total_disk_free
    if result["disk_used"]:
        result["disk_load_percent"] = (result["disk_used"]/(result["disk_used"]+result["disk_free"]))*100

    disk_loads = [
        s for s in disk_sensors
        if s.get("type") == "Load"
        and s.get("value") is not None
    ]

    disk_load_sensor = first_by_name(
        disk_loads,
        [
            "total activity",
            "total",
        ]
    )

    if disk_load_sensor:
        result["disk_load_percent"] = value_of(disk_load_sensor)
    else:
        disk_activity_sensors = [
            s for s in disk_loads
            if (
                "activity" in sensor_name(s)
                or "active" in sensor_name(s)
                or "load" in sensor_name(s)
                or "usage" in sensor_name(s)
            )
            and "used space" not in sensor_name(s)
        ]

        if disk_activity_sensors:
            result["disk_load_percent"] = max(value_of(s) for s in disk_activity_sensors)'''

    # =====================
    # Приводим типы
    # =====================

    integer_keys = {
        "cpu_water_pump_fan",
        "cpu_fan",
        "case_fan",
        "net_uploaded",
        "net_downloaded",
        "ram_load",
        "ram_total",
        "ram_free",
        "gpu_memory",
        "disk_used",
        "disk_free",
    }

    for key in METRIC_KEYS:
        value = result.get(key, 0)

        if value is None:
            result[key] = 0
        elif key in integer_keys:
            result[key] = int(value)
        else:
            result[key] = round(float(value), 2)

    return result

def fetch(config: dict | None) -> dict:
    try:
        r = requests.get(LHM_URL, timeout=3)
        r.raise_for_status()
        return get_system_metrics(r.json(), gpu_hadware_id = None, pump_identifier_id = '/lpc/nct6701d/0/fan/6')
    except Exception as e:
        print("\nНе удалось получить данные от LibreHardwareMonitor.")
        print("Проверьте:")
        print("1. LibreHardwareMonitor запущен от администратора.")
        print("2. Включён Remote/Web Server.")
        print("3. URL правильный, например: http://127.0.0.1:8085/data.json")
        print(f"\nОшибка: {e}")
    return {}

