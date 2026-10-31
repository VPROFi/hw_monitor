#!/usr/bin/env python3
import glob
import time
import threading

# Глобальные переменные для кэширования последнего измерения
_last_power_value = 0.0
_is_measuring = False
_measurement_lock = threading.Lock()

def _measure_power_in_background(interval=0.5):
    """
    Фоновая функция, которая выполняет измерение энергопотребления.
    Запускается в отдельном потоке.
    """
    global _last_power_value, _is_measuring
    
    try:
        # Ищем файлы energy_uj для основных пакетов CPU
        energy_files = glob.glob('/sys/class/powercap/intel-rapl:[0-9]/energy_uj')
        
        if energy_files:
            def read_total_energy():
                total = 0
                for f_path in energy_files:
                    try:
                        with open(f_path, 'r') as f:
                            total += int(f.read().strip())
                    except Exception:
                        continue
                return total
            
            def read_max_energy():
                total_max = 0
                for f_path in energy_files:
                    max_path = f_path.replace('energy_uj', 'max_energy_range_uj')
                    try:
                        with open(max_path, 'r') as f:
                            total_max += int(f.read().strip())
                    except Exception:
                        continue
                return total_max
            
            # Первое измерение
            energy1 = read_total_energy()
            if energy1 > 0:
                # Ждем указанный интервал
                time.sleep(interval)
                
                # Второе измерение
                energy2 = read_total_energy()
                max_range = read_max_energy()
                
                # Обработка переполнения счетчика (wrap-around)
                if energy2 < energy1 and max_range > 0:
                    delta_uj = (max_range - energy1) + energy2
                else:
                    delta_uj = energy2 - energy1
                
                # Переводим микроджоули в Ватты
                power_watts = (delta_uj / 1_000_000.0) / interval
                _last_power_value = round(power_watts, 1)
        else:
            # Fallback: пробуем через hwmon
            power_files = glob.glob('/sys/class/hwmon/hwmon*/power1_average')
            for f_path in power_files:
                try:
                    with open(f_path, 'r') as f:
                        val = int(f.read().strip())
                        if val > 0:
                            _last_power_value = round(val / 1_000_000.0, 1)
                            break
                except Exception:
                    continue
    except Exception as e:
        print(f"Ошибка измерения CPU power: {e}")
    finally:
        # Снимаем флаг измерения
        with _measurement_lock:
            _is_measuring = False

def get_cpu_power_native(interval=0.5):
    """
    Возвращает последнее измеренное значение CPU power (Ватты).
    При первом вызове возвращает 0 и запускает фоновое измерение.
    При последующих вызовах возвращает значение из предыдущего измерения
    и запускает новое измерение (если предыдущее завершилось).
    
    Args:
        interval: Интервал измерения в секундах (по умолчанию 0.5)
    
    Returns:
        float: Мощность в Ваттах (0.0 при первом вызове)
    """
    global _is_measuring, _last_power_value
    
    # Проверяем, не запущено ли уже измерение
    with _measurement_lock:
        if not _is_measuring:
            # Устанавливаем флаг и запускаем новый поток
            _is_measuring = True
            thread = threading.Thread(
                target=_measure_power_in_background,
                args=(interval,),
                daemon=True  # Поток завершится при выходе из программы
            )
            thread.start()
    
    # Возвращаем последнее измеренное значение
    return _last_power_value


# Пример использования
if __name__ == "__main__":
    print("Тест асинхронного измерения CPU power:")
    
    # Первый вызов - вернет 0, но запустит измерение
    power1 = get_cpu_power_native(interval=0.5)
    print(f"1-й вызов: {power1} W (ожидается 0)")
    
    # Ждем, чтобы измерение успело завершиться
    #time.sleep(1)
    
    # Второй вызов - вернет значение из первого измерения
    power2 = get_cpu_power_native(interval=0.5)
    print(f"2-й вызов: {power2} W (значение из 1-го измерения)")
    
    # Ждем снова
    #time.sleep(1)
    
    # Третий вызов - вернет значение из второго измерения
    power3 = get_cpu_power_native(interval=0.5)
    print(f"3-й вызов: {power3} W (значение из 2-го измерения)")

    time.sleep(3)
