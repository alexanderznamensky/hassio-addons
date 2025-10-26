# Bluetooth JDY-33 Relay Bridge (Home Assistant add-on)

MQTT-мост для Bluetooth-модулей **JDY-33-BLE** (совместим с BT05 / JDY-08, но не проверено), работающих по BLE (GATT).  

Позволяет управлять реле прямо из Home Assistant — **без rfcomm, без SPP-порта и без телефона**.

Аддон публикует в Home Assistant **MQTT-свитч** через Discovery и управляет реле по BLE (через GATT-характеристику).

---

## ⚙️ Установка
Локально:

1. Скопируйте папку `bluetooth-jdy33-relay-bridge` в каталог `/addons/` вашего Home Assistant.  
2. В интерфейсе HA:  
   **Settings → Add-ons → Local add-ons → Bluetooth JDY-33 Relay Bridge → Install**
3. Откройте аддон, настройте параметры и нажмите **Start**.

Через магазин дополнений:

1. Добавьте репозиторий https://github.com/alexanderznamensky/home-assistant-addons в магазине дополнений.
2. В интерфейсе HA:  
   **Settings → Add-ons → Home Assistant Addons → Bluetooth JDY-33 Relay Bridge → Install**
3. Откройте аддон, настройте параметры и нажмите **Запустить**.

---

## 🔌 Настройка
| Параметр | Тип | Значение по умолчанию | Описание |
|-----------|------|----------------------|-----------|
| `MQTT_HOST` | str | `core-mosquitto` | Адрес MQTT-брокера |
| `MQTT_PORT` | int | `1883` | Порт брокера |
| `MQTT_USER` / `MQTT_PASS` | str | — | Данные авторизации |
| `MQTT_PREFIX` | str | `bluetoothrelay` | Префикс MQTT-топиков |
| `RELAY_NAME` | str | `Bluetooth JDY-33 Relay` | Имя устройства |
| `RELAY_ID` | str | `jdy33_relay` | Уникальный ID в HA |
| `BLE_ADDR` | str | — | MAC-адрес модуля (например `01:B6:EC:11:EF:26`) |
| `BLE_NAME` | str | `JDY` | Имя устройства, если адрес не указан |
| `BLE_WRITE_CHAR` | str | `0000ffe1-0000-1000-8000-00805f9b34fb` | UUID характеристики записи |
| `CONNECTION_MODE` | bool | `false` | 🔁 Режим подключения: **off** = ON_DEMAND (подключение по команде), **on** = PERSISTENT (держать постоянно) |
| `IDLE_DISCONNECT_SEC` | int | `5` | Время простоя до разрыва BLE-соединения (активно только в ON_DEMAND) |
| `CMD_ON_HEX` | str | `A00101A2` | HEX-команда включения |
| `CMD_OFF_HEX` | str | `A00100A1` | HEX-команда выключения |

---

## 📡 Темы MQTT
| Назначение | Топик | Payload |
|-------------|--------|----------|
| **Command** | `<MQTT_PREFIX>/command` | `ON` / `OFF` / `RAW:<HEX>` / `DISCONNECT` |
| **State** | `<MQTT_PREFIX>/state` | `ON` / `OFF` |
| **Availability** | `<MQTT_PREFIX>/availability` | `online` / `offline` |

---

## По умолчанию HEX:
- ON: `A0 01 01 A2`
- OFF: `A0 01 00 A1`

## 🧩 MQTT Discovery

---

Аддон автоматически публикует конфигурацию для Home Assistant в топике.
