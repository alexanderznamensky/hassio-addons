#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, threading, binascii, json, asyncio, signal, atexit
from typing import Optional
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion, MQTTv311
from threading import Thread, Lock

# ---------- helpers ----------
def env_or(name: str, default: str):
    v = os.getenv(name)
    return v if (v is not None and v != "") else default

# ---------- config ----------
MQTT_HOST = env_or("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(env_or("MQTT_PORT", "1883"))
MQTT_USER = env_or("MQTT_USER", "")
MQTT_PASS = env_or("MQTT_PASS", "")
MQTT_PREFIX = env_or("MQTT_PREFIX", "jdy33relay").rstrip("/")
RELAY_NAME = env_or("RELAY_NAME", "JDY-33 Relay")
RELAY_ID = env_or("RELAY_ID", "jdy33_relay")

BLE_ADDR = env_or("BLE_ADDR", "").strip()
BLE_NAME = env_or("BLE_NAME", "JDY").strip()
BLE_WRITE_CHAR = env_or("BLE_WRITE_CHAR", "0000ffe1-0000-1000-8000-00805f9b34fb")

# CONNECTION_MODE: поддерживаем enum и/или bool
raw_mode = env_or("CONNECTION_MODE", "ON_DEMAND").strip()
lm = raw_mode.lower()
if lm in ("persistent", "true", "1", "yes", "on"):
    CONNECTION_MODE = "PERSISTENT"
elif lm in ("on_demand", "false", "0", "no", "off", ""):
    CONNECTION_MODE = "ON_DEMAND"
else:
    CONNECTION_MODE = raw_mode.upper()

IDLE_DISCONNECT_SEC = int(env_or("IDLE_DISCONNECT_SEC", "5"))  # по умолчанию 5 сек (для ON_DEMAND)

CONNECT_RETRY_SEC = int(env_or("CONNECT_RETRY_SEC", "5"))
WRITE_RETRY = int(env_or("WRITE_RETRY", "2"))

CMD_ON_HEX = env_or("CMD_ON_HEX", "A00101A2").replace(" ", "")
CMD_OFF_HEX = env_or("CMD_OFF_HEX", "A00100A1").replace(" ", "")

CMD_TOPIC = f"{MQTT_PREFIX}/command"
STATE_TOPIC = f"{MQTT_PREFIX}/state"
AVAIL_TOPIC = f"{MQTT_PREFIX}/availability"
DISCOVERY_TOPIC = f"homeassistant/switch/{RELAY_ID}/config"
DISCOVERY_PAYLOAD = {
    "name": RELAY_NAME,
    "unique_id": RELAY_ID,
    "command_topic": CMD_TOPIC,
    "state_topic": STATE_TOPIC,
    "availability_topic": AVAIL_TOPIC,
    "payload_on": "ON",
    "payload_off": "OFF",
    "state_on": "ON",
    "state_off": "OFF",
    "optimistic": True,
    "qos": 0,
    "device_class": "switch",
    "device": {
        "identifiers": [RELAY_ID],
        "manufacturer": "JDY",
        "model": "JDY-33-BLE",
        "name": RELAY_NAME,
    },
}

# ---------- BLE transport ----------
class BLETransport:
    """
    BLE через bleak с фоновым event loop.
    Режимы:
      - ON_DEMAND: ленивое подключение, авто-отключение после IDLE_DISCONNECT_SEC.
      - PERSISTENT: держим подключение постоянно (idle-таймер отключён).
    """
    def __init__(self, ble_addr: str, write_char: str, ble_name: str = ""):
        self.ble_addr = (ble_addr or "").strip()
        self.ble_name = (ble_name or "").strip()
        self.write_char = write_char

        self._client = None
        self._loop = None
        self._thread = None
        self._connect_lock = Lock()
        self._last_activity = 0.0
        self._idle_timer: Optional[threading.Timer] = None
        self._stopping = False

    # event loop
    def _ensure_loop(self):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()

    def _run(self, coro, timeout: float = 20.0):
        self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    # coroutines
    async def _ac_scan_pick(self):
        from bleak import BleakScanner
        devices = await BleakScanner.discover(timeout=8.0)
        # приоритет: точное имя -> подстрока -> JDY-алиасы
        if self.ble_name:
            for d in devices:
                if (d.name or "").strip() == self.ble_name:
                    return d.address
            for d in devices:
                n = (d.name or "").strip()
                if self.ble_name.lower() in n.lower():
                    return d.address
        aliases = ("JDY", "JDY-33", "JDY_33", "BT05", "BT05-A", "BT04", "JDY-08")
        for d in devices:
            n = (d.name or "").strip()
            if any(a.lower() in n.lower() for a in aliases):
                return d.address
        return None

    async def _ac_connect(self):
        from bleak import BleakClient, BleakScanner
        if self._client and self._client.is_connected:
            return
        addr = self.ble_addr
        if not addr:
            # нет адреса — найдём через скан
            addr = await self._ac_scan_pick()
            if not addr:
                raise RuntimeError("BLE: устройство не найдено при сканировании (задайте BLE_ADDR или BLE_NAME).")
            print(f"[BLE] Found via scan: {addr}")
            self.ble_addr = addr

        # Попытка №1: прямое подключение
        try:
            self._client = BleakClient(addr, timeout=10.0)
            await self._client.connect()
            print("[BLE] Connected")
            return
        except Exception as e:
            print(f"[BLE] Connect failed ({e}); rescanning and retrying...")

        # Попытка №2: сделать короткий скан, затем повторить connect
        try:
            try:
                await BleakScanner.discover(timeout=6.0)
            except Exception:
                pass
            self._client = BleakClient(addr, timeout=10.0)
            await self._client.connect()
            print("[BLE] Connected (after rescan)")
        except Exception as e2:
            # окончательный фейл — пробросим наверх
            raise RuntimeError(f"BLE: не удалось подключиться к {addr}: {e2}")

    async def _ac_disconnect(self):
        if self._client:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
                    print("[BLE] Disconnected")
            finally:
                self._client = None

    async def _ac_write(self, data: bytes):
        if not self._client or not self._client.is_connected:
            raise RuntimeError("BLE: клиент не подключён")
        await self._client.write_gatt_char(self.write_char, data, response=False)

    async def _ac_is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    # idle
    def _arm_idle_timer(self):
        if self._stopping:
            return
        if CONNECTION_MODE == "PERSISTENT":
            return  # idle-таймер не нужен
        if IDLE_DISCONNECT_SEC <= 0:
            return
        if self._idle_timer:
            self._idle_timer.cancel()
        self._idle_timer = threading.Timer(IDLE_DISCONNECT_SEC, self._idle_disconnect_if_idle)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _idle_disconnect_if_idle(self):
        try:
            if self._stopping or CONNECTION_MODE == "PERSISTENT":
                return
            now = time.time()
            if (now - self._last_activity) >= IDLE_DISCONNECT_SEC:
                try:
                    self._run(self._ac_disconnect(), timeout=5.0)
                except Exception as e:
                    print(f"[BLE] Idle disconnect error: {e}")
        finally:
            pass

    # facade
    def ensure_connected(self):
        with self._connect_lock:
            if self._stopping:
                raise RuntimeError("BLE: stopping")
            if not self.healthy():
                self._run(self._ac_connect(), timeout=25.0)

    def open(self):
        if CONNECTION_MODE == "PERSISTENT":
            # подключаемся сразу
            self.ensure_connected()

    def close(self):
        self._stopping = True
        try:
            if self._idle_timer:
                self._idle_timer.cancel()
        except Exception:
            pass
        try:
            self._run(self._ac_disconnect(), timeout=5.0)
        except Exception:
            pass

    def write(self, data: bytes) -> None:
        # и в ON_DEMAND, и в PERSISTENT гарантируем соединение перед записью
        self.ensure_connected()
        self._last_activity = time.time()
        try:
            self._run(self._ac_write(data), timeout=5.0)
        finally:
            self._arm_idle_timer()

    def healthy(self) -> bool:
        try:
            return bool(self._run(self._ac_is_connected(), timeout=2.0))
        except Exception:
            return False

# ---------- bridge ----------
class JDY33Bridge:
    def __init__(self, transport: BLETransport, mqtt_client: mqtt.Client):
        self.t = transport
        self.mqtt = mqtt_client
        self.state = "OFF"
        self._stopping = False

    def publish_discovery(self):
        self.mqtt.publish(DISCOVERY_TOPIC, json.dumps(DISCOVERY_PAYLOAD), retain=True)
        self.mqtt.publish(AVAIL_TOPIC, "online", retain=True)
        self.mqtt.publish(STATE_TOPIC, self.state, retain=True)

    def _hexstr_to_bytes(self, hexstr: str) -> bytes:
        try:
            return binascii.unhexlify(hexstr)
        except binascii.Error:
            raise ValueError(f"Неверная HEX-строка: {hexstr}")

    def _send(self, payload_hex: str) -> bool:
        data = self._hexstr_to_bytes(payload_hex)
        for i in range(1 + WRITE_RETRY):
            try:
                self.t.write(data)
                return True
            except Exception as e:
                if i >= WRITE_RETRY:
                    print(f"[JDY33] Ошибка при отправке: {e}")
                    return False
                time.sleep(0.2)
        return False

    def handle_command(self, cmd: str):
        cmd = cmd.strip().upper()
        if cmd == "ON":
            if self._send(CMD_ON_HEX):
                self.state = "ON"; self.mqtt.publish(STATE_TOPIC, "ON", retain=True)
        elif cmd == "OFF":
            if self._send(CMD_OFF_HEX):
                self.state = "OFF"; self.mqtt.publish(STATE_TOPIC, "OFF", retain=True)
        elif cmd.startswith("RAW:"):
            hexbody = cmd[4:].replace(" ", "")
            self._send(hexbody)
        elif cmd == "DISCONNECT":
            try:
                self.t.close()
            except Exception:
                pass
        else:
            print(f"[JDY33] Неизвестная команда: {cmd}")

    def shutdown(self):
        if self._stopping:
            return
        self._stopping = True
        try:
            self.mqtt.publish(AVAIL_TOPIC, "offline", retain=True)
        except Exception:
            pass
        try:
            self.t.close()
        except Exception:
            pass

# ---------- main ----------
def main():
    client = mqtt.Client(protocol=MQTTv311, callback_api_version=CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.will_set(AVAIL_TOPIC, "offline", retain=True)

    transport = BLETransport(ble_addr=BLE_ADDR, write_char=BLE_WRITE_CHAR, ble_name=BLE_NAME)
    bridge = JDY33Bridge(transport, client)

    def on_connect(cli, userdata, flags, rc, properties=None):
        print(f"[MQTT] Connected rc={rc}")
        cli.subscribe(CMD_TOPIC)
        bridge.publish_discovery()
        if CONNECTION_MODE == "PERSISTENT":
            try:
                transport.open()
            except Exception as e:
                print(f"[BLE] Initial connect failed: {e}")

    def on_message(cli, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="ignore")
        print(f"[MQTT] {msg.topic} -> {payload}")
        bridge.handle_command(payload)

    client.on_connect = on_connect
    client.on_message = on_message

    # корректное завершение
    def _graceful_exit(sig, frame):
        print(f"[SYS] Caught signal {sig}, shutting down...")
        bridge.shutdown()
        time.sleep(0.5)
        os._exit(0)

    signal.signal(signal.SIGTERM, _graceful_exit)
    signal.signal(signal.SIGINT, _graceful_exit)
    atexit.register(bridge.shutdown)

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            print(f"[MQTT] Ошибка подключения: {e}. Повтор через {CONNECT_RETRY_SEC}s")
            time.sleep(CONNECT_RETRY_SEC)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
