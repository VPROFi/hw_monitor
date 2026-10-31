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

# Определение пользователя, который вызвал sudo (или root, если вызван напрямую)
TARGET_USER=${SUDO_USER:-root}
echo -e "Установка будет выполнена для пользователя: ${GREEN}$TARGET_USER${NC}"

DEST_DIR="/opt/hw_monitor"

# 1. Создание целевой директории
echo -e "[1/6] Создание директории ${DEST_DIR}..."
mkdir -p "$DEST_DIR"

# 2. Копирование файлов проекта
echo -e "[2/6] Копирование файлов проекта..."
cp monitor.py "$DEST_DIR/"
cp -r sources "$DEST_DIR/"
cp -r smartmonitor "$DEST_DIR/"

# Опционально: копируем папку images, если она есть (требуется для hw_monitor.xml)
if [ -d "images" ]; then
    cp -r images "$DEST_DIR/"
    echo -e "  -> Папка images скопирована."
fi

# Установка правильных прав на файлы
chown -R "$TARGET_USER:$TARGET_USER" "$DEST_DIR"
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
# Дополнительно триггерим usb, чтобы правила для smartmonitor применились сразу без перезагрузки
udevadm trigger --subsystem-match=usb --action=add
echo -e "  -> Правила udev успешно применены."

# 5. Установка и настройка systemd службы
echo -e "[5/6] Настройка systemd службы..."
# Заменяем плейсхолдер на реальное имя пользователя
sed -i "s/REPLACE_WITH_USER/$TARGET_USER/g" hw_monitor.service

# Копируем файл службы в систему
cp hw_monitor.service /etc/systemd/system/

# Перезагружаем демон systemd
systemctl daemon-reload

# 6. Включение и запуск службы
echo -e "[6/6] Включение и запуск службы hw_monitor..."
systemctl enable hw_monitor.service
systemctl restart hw_monitor.service

echo -e "${GREEN}=== Установка успешно завершена! ===${NC}"
echo -e "Проверить статус службы можно командой: ${YELLOW}sudo systemctl status hw_monitor${NC}"
echo -e "Просмотреть логи в реальном времени: ${YELLOW}sudo journalctl -u hw_monitor -f${NC}"
