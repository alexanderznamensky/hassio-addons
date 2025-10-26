# Bluetooth JDY-33 Relay Bridge (Home Assistant add-on)

MQTT-мост для Bluetooth-модулей JDY-33-BLE (BT05 / JDY-08 - работа не проверена), работающих по BLE (GATT).
Позволяет управлять реле прямо из Home Assistant — без rfcomm, без SPP-порта и без телефона.
Публикует свитч в Home Assistant через MQTT Discovery и управляет реле по BLE (GATT).

## Установка
1. Скопируйте папку `jdy33-relay-ble` в каталог `/addons/` на вашем Home Assistant.
2. В HA: Settings → Add-ons → Local add-ons → Bluetooth JDY-33 Relay Bridge → Install.
3. Откройте аддон и настройте конфигурацию.
4. Start.

## Темы MQTT
- Command: `<MQTT_PREFIX>/command` (ON/OFF, RAW:<HEX>)
- State: `<MQTT_PREFIX>/state` (ON/OFF)
- Availability: `<MQTT_PREFIX>/availability` (online/offline)

## По умолчанию HEX:
- ON: `A0 01 01 A2`
- OFF: `A0 01 00 A1`

## Примечания
- Для BLE аддону включены `host_dbus: true` и `privileged` — требуется для доступа к BlueZ.
