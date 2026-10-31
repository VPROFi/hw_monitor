#!/usr/bin/env python3
import glob
import time
import threading
import string
import shutil

# Глобальные переменные для кэширования последнего измерения
_last_values = [0,0]
_is_measuring = False
_measurement_lock = threading.Lock()

def _get_disk_usage():
    print('-'*100, 'detect disk size\n', '-'*100)
    values = [0,0]
    try:
        for item in string.ascii_uppercase[2:]:
            try:
                usage = shutil.disk_usage(f'{item}:\\')
                values[0] += usage.used
                values[1] += usage.free
            except:
                continue
    except Exception as e:
        print(f"Ошибка измерения места на всех дисках: {e}")
    return values

def _measure_usage_in_background(interval=10.0):
    """
    Фоновая функция, которая вычисляет место на диске
    Запускается в отдельном потоке.
    """
    global _last_values, _is_measuring, _measurement_lock

    time.sleep(interval)
    _last_values = _get_disk_usage()
    # Снимаем флаг измерения
    with _measurement_lock:
        _is_measuring = False

def get_all_disks_usage(interval=10.0):
    """
    Возвращает последнее измеренное значение
    При первом вызове возвращает 0 и запускает фоновое измерение.
    При последующих вызовах возвращает значение из предыдущего измерения
    и запускает новое измерение (если предыдущее завершилось).
    
    Args:
        interval: Интервал измерения в секундах (по умолчанию 0.5)
    
    Returns:
        int, int: disk_used, disk_free
    """
    global _is_measuring, _last_values
    
    # Проверяем, не запущено ли уже измерение
    with _measurement_lock:
        if not _is_measuring:
            # Устанавливаем флаг и запускаем новый поток
            _is_measuring = True
            if _last_values == [0,0]:
                _last_values = _get_disk_usage()
            thread = threading.Thread(
                target=_measure_usage_in_background,
                args=(interval,),
                daemon=True  # Поток завершится при выходе из программы
            )
            thread.start()
    
    # Возвращаем последнее измеренное значение
    return _last_values


# Пример использования
if __name__ == "__main__":
    print("Тест асинхронного измерения места на диске:")
    
    # Первый вызов - вернет 0, но запустит измерение
    values = get_all_disks_usage(interval=10)
    print(f"1-й вызов: {values} (ожидается 0, 0)")
    
    # Ждем 
    time.sleep(1)
    
    # Второй вызов - поскольку недождались вернет значение 0,0
    values = get_all_disks_usage(interval=10)
    print(f"2-й вызов: {values} (ожидается 0, 0)")
    
    # Ждем снова
    time.sleep(15)
    
    # Третий вызов - вернет значение из первого измерения
    values = get_all_disks_usage(interval=10)
    print(f"3-й вызов: {values} (значение из 1-го измерения)")

