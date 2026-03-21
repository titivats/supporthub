from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency
    mqtt = None
from python.iot_monitor.iot_monitor_parser import (
    parse_payload_numeric_map,
    pick_metric_value,
    to_iso,
)
from python.iot_monitor.iot_monitor_storage import (
    insert_measurement_row,
    insert_status_log_row,
)


@dataclass
class _Sample:
    ts: datetime
    value: float


class IoTMonitorService:
    def __init__(self) -> None:
        self.host = os.getenv("SUPPORTHUB_MQTT_HOST", "10.206.9.201").strip() or "10.206.9.201"
        self.port = int(os.getenv("SUPPORTHUB_MQTT_PORT", "1883"))
        self.topic = os.getenv("SUPPORTHUB_MQTT_TOPIC", "power/pzem").strip() or "power/pzem"
        self.client_id = os.getenv("SUPPORTHUB_MQTT_CLIENT_ID", "SUPPORTHUB-IOT-MONITOR").strip() or "SUPPORTHUB-IOT-MONITOR"
        self.sample_limit = int(os.getenv("SUPPORTHUB_IOT_SAMPLE_LIMIT", "180"))

        self._lock = threading.Lock()
        self._client = None
        self._started = False

        self.connected = False
        self.last_error = ""
        self.last_payload = "-"
        self.last_message_at: datetime | None = None
        self.message_count = 0
        self.parse_error_count = 0
        self.latest_values: Dict[str, float] = {}
        self.series: Dict[str, deque[_Sample]] = {}

    def _build_status_log_row(self, recorded_at: datetime) -> Dict[str, Any]:
        return {
            "recorded_at": recorded_at,
            "broker": f"{self.host}:{self.port}",
            "topic": self.topic,
            "mqtt_client": self.client_id,
            "connected": self.connected,
            "last_message_at": self.last_message_at,
            "message_count": int(self.message_count),
            "parse_error_count": int(self.parse_error_count),
            "last_payload": self.last_payload,
            "last_error": self.last_error,
        }

    def _build_measurement_row(
        self,
        recorded_at: datetime,
        payload: str,
        numeric_map: Dict[str, float],
    ) -> Dict[str, Any]:
        return {
            "recorded_at": recorded_at,
            "broker": f"{self.host}:{self.port}",
            "topic": self.topic,
            "mqtt_client": self.client_id,
            "voltage": pick_metric_value(numeric_map, ("voltage", "volt", "volts", "v")),
            "current": pick_metric_value(numeric_map, ("current", "ampere", "amperes", "amps", "amp", "a")),
            "power": pick_metric_value(numeric_map, ("power", "watt", "watts", "w")),
            "power_factor": pick_metric_value(numeric_map, ("powerfactor", "power_factor", "pf")),
            "energy": pick_metric_value(numeric_map, ("energy", "kwh", "wh")),
            "frequency": pick_metric_value(numeric_map, ("frequency", "freq", "hz", "f")),
            "raw_payload": payload or None,
        }

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self.last_error = ""

            if mqtt is None:
                self.last_error = "Missing dependency: paho-mqtt"
                return

            try:
                # paho-mqtt v2 supports callback_api_version; v1 does not.
                try:
                    self._client = mqtt.Client(
                        mqtt.CallbackAPIVersion.VERSION2,
                        client_id=self.client_id,
                        protocol=mqtt.MQTTv311,
                    )
                except Exception:
                    self._client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)

                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.on_message = self._on_message
                self._client.connect_async(self.host, self.port, keepalive=30)
                self._client.loop_start()
                self._started = True
            except Exception as exc:
                self.last_error = f"MQTT setup failed: {exc}"
                self._client = None
                self._started = False

    def reconnect(self, host: str | None = None, port: int | None = None,
                  topic: str | None = None, client_id: str | None = None) -> Dict[str, Any]:
        """Stop, update config, restart. Returns new config dict."""
        self.stop()
        with self._lock:
            if host is not None:
                self.host = host.strip() or self.host
            if port is not None:
                self.port = port
            if topic is not None:
                self.topic = topic.strip() or self.topic
            if client_id is not None:
                self.client_id = client_id.strip() or self.client_id
            # Clear old data
            self.latest_values.clear()
            self.series.clear()
            self.message_count = 0
            self.parse_error_count = 0
            self.last_payload = "-"
            self.last_message_at = None
            self.last_error = ""
        self.start()
        return {
            "host": self.host,
            "port": self.port,
            "topic": self.topic,
            "client_id": self.client_id,
        }

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._started = False
            client = self._client
            self._client = None

        if client is not None:
            try:
                client.loop_stop()
            except Exception:
                pass
            try:
                client.disconnect()
            except Exception:
                pass

        with self._lock:
            self.connected = False

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            trend_out: Dict[str, list[Dict[str, Any]]] = {}
            for key, q in self.series.items():
                trend_out[key] = [{"ts": to_iso(s.ts), "value": s.value} for s in q]

            return {
                "broker": f"{self.host}:{self.port}",
                "topic": self.topic,
                "client_id": self.client_id,
                "connected": self.connected,
                "last_error": self.last_error,
                "last_message_at": to_iso(self.last_message_at),
                "last_payload": self.last_payload,
                "message_count": self.message_count,
                "parse_error_count": self.parse_error_count,
                "latest_values": dict(self.latest_values),
                "trend": trend_out,
                "samples": max((len(v) for v in self.series.values()), default=0),
            }

    # MQTT callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
        now = datetime.utcnow()
        rc = getattr(reason_code, "value", reason_code)
        status_row: Dict[str, Any]
        with self._lock:
            if int(rc) == 0:
                self.connected = True
                self.last_error = ""
                try:
                    client.subscribe(self.topic, qos=0)
                except Exception as exc:
                    self.connected = False
                    self.last_error = f"MQTT subscribe failed: {exc}"
            else:
                self.connected = False
                self.last_error = f"MQTT connect failed (reason_code={reason_code})"
            status_row = self._build_status_log_row(now)
        insert_status_log_row(status_row)

    def _on_disconnect(self, client, userdata, reason_code, properties=None):  # noqa: ANN001
        now = datetime.utcnow()
        rc = getattr(reason_code, "value", reason_code)
        status_row: Dict[str, Any]
        with self._lock:
            self.connected = False
            if int(rc) != 0:
                self.last_error = f"MQTT disconnected (reason_code={reason_code})"
            status_row = self._build_status_log_row(now)
        insert_status_log_row(status_row)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        try:
            payload = (msg.payload or b"").decode("utf-8", errors="replace").strip()
        except Exception:
            payload = str(msg.payload)

        now = datetime.utcnow()
        numeric_map: Dict[str, float] = parse_payload_numeric_map(payload)

        status_row: Dict[str, Any]
        measurement_row: Dict[str, Any]
        with self._lock:
            self.last_payload = payload or "-"
            self.last_message_at = now
            self.message_count += 1

            if not numeric_map:
                self.parse_error_count += 1
            else:
                for key, val in numeric_map.items():
                    self.latest_values[key] = val
                    if key not in self.series:
                        self.series[key] = deque(maxlen=self.sample_limit)
                    self.series[key].append(_Sample(ts=now, value=val))
            status_row = self._build_status_log_row(now)
            measurement_row = self._build_measurement_row(now, payload, numeric_map)
        insert_status_log_row(status_row)
        insert_measurement_row(measurement_row)


iot_monitor = IoTMonitorService()
