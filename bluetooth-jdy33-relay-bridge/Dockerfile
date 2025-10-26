FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      bluez bluez-tools bluetooth \
      rfkill dbus jq bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY jdy33_mqtt_bridge.py run.sh ./
RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
