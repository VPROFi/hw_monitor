#!/bin/bash
set -e # Остановить выполнение при любой ошибке

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # Без цвета

echo -e "${YELLOW}=== Установка SmartMonitor HW Monitor ===${NC}"

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
  echo -e "Пожалуйста, запустите скрипт от имени root (используйте sudo)"
  exit 1
fi

DEST_DIR="/opt/hw_monitor"

# 1. Создание целевой директории
echo -e "[1/6] Создание директории ${DEST_DIR}..."
mkdir -p "$DEST_DIR"

# 2. Копирование файлов проекта
echo -e "[2/6] Копирование файлов проекта..."
cp monitor.py "$DEST_DIR/"
cp -r sources "$DEST_DIR/"
cp -r smartmonitor "$DEST_DIR/"

# Установка прав на исполнение (владельцем остается root)
chmod +x "$DEST_DIR/monitor.py"

# 3. Копирование udev правил
echo -e "[3/6] Установка udev правил..."
cp ./linux/99-powercap.rules /etc/udev/rules.d/
cp ./linux/99-smartmonitor.rules /etc/udev/rules.d/
echo -e "  -> Правила скопированы в /etc/udev/rules.d/"

# 4. Перезагрузка правил udev и триггер
echo -e "[4/6] Применение правил udev..."
udevadm control --reload-rules
udevadm trigger --subsystem-match=powercap --action=add
udevadm trigger --subsystem-match=usb --action=add
echo -e "  -> Правила udev успешно применены."

# 5. Установка systemd службы
echo -e "[5/6] Настройка systemd службы..."
cp ./linux/hw_monitor.service /etc/systemd/system/
systemctl daemon-reload

# 6. Включение и запуск службы
echo -e "[6/6] Включение и запуск службы hw_monitor..."
systemctl enable hw_monitor.service
systemctl restart hw_monitor.service

echo -e "${GREEN}=== Установка успешно завершена! ===${NC}"
echo -e "Служба работает от имени root."
echo -e "Проверить статус: ${YELLOW}sudo systemctl status hw_monitor${NC}"
echo -e "Просмотр логов: ${YELLOW}sudo journalctl -u hw_monitor -f${NC}"
