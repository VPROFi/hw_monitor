#!/usr/bin/env python3
import glob
import time
import os
import subprocess
try:
    from .get_power_native import get_cpu_power_native
    from .get_temperatures import cpu_temperature
    from .tags import TAGS
except:
    from get_power_native import get_cpu_power_native
    from get_temperatures import cpu_temperature
    from tags import TAGS

def fetch(config: dict | None) -> dict:

    METRIC_KEYS = tuple(TAGS.keys())

    result = {key: 0 for key in METRIC_KEYS}

    def get_cpu_metrics_native(interval=1.0):
        '''
        Возвращает кортеж: (максимальная частота ядра в МГц, общая загрузка CPU в %)
        Работает только в Linux.
        '''
        # 1. Максимальная частота ядра
        # Ищем файлы текущей частоты для всех ядер
        freq_files = glob.glob('/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq')
        max_freq_khz = 0
        
        for file_path in freq_files:
            try:
                with open(file_path, 'r') as f:
                    # Значение в файле хранится в килогерцах (kHz)
                    freq = int(f.read().strip())
                    if freq > max_freq_khz:
                        max_freq_khz = freq
            except (ValueError, IOError):
                continue
                
        # Переводим в мегагерцы (МГц)
        max_freq_mhz = max_freq_khz / 1000.0
        
        # 2. Общая загруженность процессора
        # Вспомогательная функция для чтения общих тиков CPU из /proc/stat
        def read_cpu_times():
            with open('/proc/stat', 'r') as f:
                for line in f:
                    if line.startswith('cpu '):
                        parts = line.split()
                        # parts[0] = 'cpu'
                        # parts[1..] = user, nice, system, idle, iowait, irq, softirq, steal
                        idle = int(parts[4]) + int(parts[5])  # idle + iowait
                        total = sum(int(x) for x in parts[1:])
                        return idle, total
            return 0, 0
    
        # Делаем первый замер
        idle1, total1 = read_cpu_times()
        
        # Ждем указанный интервал
        time.sleep(interval)
        
        # Делаем второй замер
        idle2, total2 = read_cpu_times()
        
        # Считаем разницу (дельту)
        idle_delta = idle2 - idle1
        total_delta = total2 - total1
        
        if total_delta == 0:
            usage_percent = 0.0
        else:
            # Процент загрузки = (время не простоя / общее время) * 100
            usage_percent = (1.0 - idle_delta / total_delta) * 100.0
            
        return max_freq_mhz, usage_percent

    def get_ram_usage_native():
        '''
        Читает /proc/meminfo и считает занятую память.
        Возвращает кортеж: (занято МБ, всего МБ, процент загрузки)
        '''
        meminfo = {}
        
        # 1. Парсим /proc/meminfo
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        # Значения в /proc/meminfo всегда в kB
                        value = int(parts[1]) 
                        meminfo[key] = value
        except IOError:
            return 0, 0, 0.0
    
        # 2. Достаем нужные значения
        total_kb = meminfo.get('MemTotal', 0)
        
        # MemAvailable - это память, которую реально можно отдать новым программам
        # (включает MemFree + часть кэша, который можно сбросить)
        available_kb = meminfo.get('MemAvailable', 0) 
        
        # Если ядро очень старое (< 3.14) и MemAvailable нет, делаем грубую прикидку
        if available_kb == 0:
            free_kb = meminfo.get('MemFree', 0)
            buffers_kb = meminfo.get('Buffers', 0)
            cached_kb = meminfo.get('Cached', 0)
            available_kb = free_kb + buffers_kb + cached_kb
    
        # 3. Считаем занятое
        used_kb = total_kb - available_kb
        
        # Считаем процент
        percent = (used_kb / total_kb) * 100.0 if total_kb > 0 else 0.0
        
        return used_kb*1024, total_kb*1024, percent

    def get_info_list_native(path):

        items = {}
        
        for file_path in glob.glob(path):
            try:
                with open(file_path, 'r') as f:
                    value = int(f.read().strip())
                    if value > 0:
                        # Используем имя файла (например, fan1_input) как ключ
                        name = file_path.split('/')[-1] 
                        items[name] = value
            except (ValueError, IOError, PermissionError):
                continue
                
        return items

    def get_disk_usage(mount_point='/home'):
        '''
        Возвращает информацию о диске, смонтированном в указанной точке.
        Возвращает кортеж: (всего, использовано, процент использования)
        '''
        try:
            try:
                # Получаем статистику файловой системы
                stat = os.statvfs(mount_point)
            except:
                stat = os.statvfs('/root')
            
            # f_frsize - это фундаментальный размер блока файловой системы в байтах
            block_size = stat.f_frsize
            
            # f_blocks - общее количество блоков
            # f_bfree - общее количество свободных блоков (включая резерв для root)
            total_blocks = stat.f_blocks
            free_blocks = stat.f_bfree
            
            # Вычисляем размеры в байтах
            total_bytes = total_blocks * block_size
            free_bytes = free_blocks * block_size
            used_bytes = total_bytes - free_bytes
            
            # Переводим в гигабайты (1 ГБ = 1024^3 байт, как в Linux 'df -h')
            #gb_divisor = 1024 ** 3
            
            #total_gb = total_bytes / gb_divisor
            #used_gb = used_bytes / gb_divisor
            
            # Вычисляем процент использования
            usage_percent = (used_bytes / total_bytes) * 100.0 if total_bytes > 0 else 0.0
            
            return used_bytes, free_bytes, usage_percent
            
        except FileNotFoundError:
            print(f"Ошибка: Точка монтирования '{mount_point}' не найдена.")
            return 0.0, 0.0, 0.0
        except PermissionError:
            print(f"Ошибка: Нет прав для чтения статистики '{mount_point}'.")
            return 0.0, 0.0, 0.0
        except Exception as e:
            print(f"Непредвиденная ошибка: {e}")
            return 0.0, 0.0, 0.0

    def get_default_interface():
        '''
        Находит сетевой интерфейс, через который идет трафик в интернет (Default Route).
        '''
        try:
            with open('/proc/net/route', 'r') as f:
                next(f)  # Пропускаем заголовок таблицы
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        iface = parts[0]
                        destination = parts[1]
                        # 00000000 означает маршрут по умолчанию (весь остальной трафик)
                        if destination == '00000000':
                            return iface
        except Exception:
            pass
        return None

    def get_interface_bytes(iface):
        '''
        Читает счетчики rx_bytes (получено) и tx_bytes (отправлено) для интерфейса.
        '''
        try:
            rx_path = f'/sys/class/net/{iface}/statistics/rx_bytes'
            tx_path = f'/sys/class/net/{iface}/statistics/tx_bytes'
            
            with open(rx_path, 'r') as f:
                rx_bytes = int(f.read().strip())
            with open(tx_path, 'r') as f:
                tx_bytes = int(f.read().strip())
                
            return rx_bytes, tx_bytes
        except Exception:
            return 0, 0

    def get_nvidia_gpu_info(gpu_id=0):
        '''
        Возвращает словарь с основными параметрами GPU NVIDIA.
        Если GPU нет или nvidia-smi не установлен, возвращает None.
        '''
        # Список параметров, которые мы хотим получить
        query = "name,temperature.gpu,utilization.gpu,memory.total,memory.used,fan.speed,power.draw,clocks.current.graphics,clocks.current.memory"
        
        command = [
            "nvidia-smi",
            f"--id={gpu_id}",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits"
        ]
        
        try:
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                timeout=5, 
                check=True
            )
            
            # Результат будет строкой вида: "NVIDIA GeForce RTX 4090, 45, 12, 5, 24576, 2048, 30, 150.5"
            values = result.stdout.strip().split(", ")
            
            # Сопоставляем значения с ключами (порядок должен совпадать с query)
            keys = ["gpu_name", "gpu_temperature", "gpu_used_percent", "gpu_memory", "gpu_memory_used", "gpu_fan_percent", "gpu_power", "gpu_frequency", "gpu_memory_frequency"]
            
            gpu_data = {}
            for i, key in enumerate(keys):
                val = values[i].strip()
                # Преобразуем числовые строки в float или int, где это возможно
                if key == "gpu_name":
                    gpu_data[key] = val
                elif key == "gpu_power":
                    gpu_data[key] = float(val) if val else 0.0
                else:
                    gpu_data[key] = int(val) if val else 0
                    if key in ("gpu_memory", "gpu_memory_used"):
                        gpu_data[key] *= (1024*1024)
            gpu_data["gpu_memory_used_percent"] = int(gpu_data["gpu_memory_used"]/(gpu_data["gpu_memory"] or 1)*100)
            return gpu_data
    
        except FileNotFoundError:
            print("Ошибка: утилита 'nvidia-smi' не найдена. Установите драйверы NVIDIA.")
            return None
        except subprocess.CalledProcessError as e:
            print(f"Ошибка выполнения nvidia-smi: {e.stderr}")
            return None
        except Exception as e:
            print(f"Непредвиденная ошибка: {e}")
            return None
  
    result["cpu_temperature"] = cpu_temperature()
    result["cpu_frequency"], result["cpu_percent"] = get_cpu_metrics_native()
    result["ram_load"], result["ram_total"], result["memory_used_percent"] = get_ram_usage_native()
    result["cpu_power"] = get_cpu_power_native()
    result["ram_free"] = result["ram_total"] - result["ram_load"]
    fans = get_info_list_native('/sys/class/hwmon/hwmon*/fan*_input')
    result["cpu_fan"], result["case_fan"], result["cpu_water_pump_fan"] = fans['fan1_input'], fans['fan2_input'], fans['fan7_input']
    nvme_temp = get_info_list_native('/sys/class/nvme/nvme0/hwmon*/temp*_input')
    result["disk_temperature"] = nvme_temp['temp1_input'] / 1000.0
    result["disk_used"], result["disk_free"], result["disk_load_percent"] = get_disk_usage()

    iface = get_default_interface()
    if iface:
        result["net_downloaded"], result["net_uploaded"] = get_interface_bytes(iface)

    gpu_info = get_nvidia_gpu_info()
    if gpu_info:
       result.update(gpu_info)

    return result
