#!/usr/bin/env bash
set -euo pipefail

# ---------- DBus для BlueZ/bleak ----------
export DBUS_SYSTEM_BUS_ADDRESS=${DBUS_SYSTEM_BUS_ADDRESS:-"unix:path=/run/dbus/system_bus_socket"}
if [ ! -e "/run/dbus/system_bus_socket" ] && [ -S "/var/run/dbus/system_bus_socket" ]; then
  export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/var/run/dbus/system_bus_socket"
fi

# ---------- Читаем опции аддона ----------
if [ -f "/data/options.json" ]; then
  echo "[JDY33] Loading /data/options.json"

  export MQTT_HOST=$(jq -r '.MQTT_HOST // empty' /data/options.json)
  export MQTT_PORT=$(jq -r '.MQTT_PORT // empty' /data/options.json)
  export MQTT_USER=$(jq -r '.MQTT_USER // empty' /data/options.json)
  export MQTT_PASS=$(jq -r '.MQTT_PASS // empty' /data/options.json)
  export MQTT_PREFIX=$(jq -r '.MQTT_PREFIX // empty' /data/options.json)

  export RELAY_NAME=$(jq -r '.RELAY_NAME // empty' /data/options.json)
  export RELAY_ID=$(jq -r '.RELAY_ID // empty' /data/options.json)

  export BLE_ADDR=$(jq -r '.BLE_ADDR // empty' /data/options.json)
  export BLE_NAME=$(jq -r '.BLE_NAME // empty' /data/options.json)
  export BLE_WRITE_CHAR=$(jq -r '.BLE_WRITE_CHAR // empty' /data/options.json)

  # CONNECTION_MODE может быть enum ("ON_DEMAND"/"PERSISTENT") или bool
  export CONNECTION_MODE=$(jq -r '.CONNECTION_MODE // empty' /data/options.json)
  export IDLE_DISCONNECT_SEC=$(jq -r '.IDLE_DISCONNECT_SEC // empty' /data/options.json)

  export CMD_ON_HEX=$(jq -r '.CMD_ON_HEX // empty' /data/options.json)
  export CMD_OFF_HEX=$(jq -r '.CMD_OFF_HEX // empty' /data/options.json)
fi

# ---------- Включим BT-адаптер ----------
rfkill unblock bluetooth 2>/dev/null || true
if command -v bluetoothctl >/dev/null 2>&1; then
  bluetoothctl power on || true
  bluetoothctl show || true
fi
if command -v hciconfig >/dev/null 2>&1; then
  hciconfig hci0 up || true
fi

# ---------- Красивый лог режима (enum ИЛИ bool) ----------
LM="$(printf '%s' "${CONNECTION_MODE:-}" | tr '[:upper:]' '[:lower:]')"
MODE_NAME="ON_DEMAND"
case "$LM" in
  persistent|true|1|yes|on) MODE_NAME="PERSISTENT" ;;
  on_demand|false|0|no|off|"") MODE_NAME="ON_DEMAND" ;;
  *) MODE_NAME="${CONNECTION_MODE:-ON_DEMAND}";;  # если пришло строкой как есть
esac

echo "[JDY33] Starting BLE bridge (MODE=${MODE_NAME}, BLE_ADDR=${BLE_ADDR:-}, BLE_NAME=${BLE_NAME:-}, IDLE=${IDLE_DISCONNECT_SEC:-5}s) ..."
exec python -u /app/jdy33_mqtt_bridge.py
