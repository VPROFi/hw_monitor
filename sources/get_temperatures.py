#!/usr/bin/env python3
import glob, time, pprint
cpu_temperature_path = None
def get_all_temperatures():
    temperatures = {}
    temp_labels = glob.glob('/sys/class/hwmon/*/temp*_input')
    for file_path in temp_labels:
        with open(file_path, 'r') as f:
            temperatures[file_path] = dict()
            try:
                 temperatures[file_path]['label'] = open(file_path[:-len('_input')]+'_label', 'r').read().strip()
            except:
                 temperatures[file_path]['label'] = open(file_path[:file_path.rfind('/')]+'/name', 'r').read().strip()
            temperatures[file_path]['value'] = int(f.read().strip())

    temp_labels = glob.glob('/sys/class/thermal/thermal_zone*/temp')
    for file_path in temp_labels:
        with open(file_path, 'r') as f:
            temperatures[file_path] = dict()
            temperatures[file_path]['label'] = open(file_path[:-len('temp')]+'type', 'r').read().strip()
            temperatures[file_path]['value'] = int(f.read().strip())
    return temperatures

def cpu_temperature():
    global cpu_temperature_path
    try:
        if cpu_temperature_path is None:
            temperatures = get_all_temperatures()
            for item in temperatures:
                if temperatures[item]['label'] == ('Package id 0'):
                   cpu_temperature_path = item
        with open(cpu_temperature_path, 'r') as f:
            # В /sys/ значения всегда целые (в миллиградусах) - переводим в градусы
            return int(f.read().strip()) / 1000.0
    except Exception as e:
        print(e)
    return 0

