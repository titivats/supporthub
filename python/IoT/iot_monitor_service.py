from __future__ import annotations

import json
import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import text

from python.db import SessionLocal, engine

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency
    mqtt = None


def _to_iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


def _safe_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except Exception:
            return None
    return None


def _extract_numeric(obj: Any, prefix: str = "", out: Dict[str, float] | None = None) -> Dict[str, float]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _extract_numeric(v, key, out)
        return out
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]" if prefix else f"[{i}]"
            _extract_numeric(v, key, out)
        return out
    num = _safe_float(obj)
    if num is not None:
        out[prefix or "value"] = num
    return out


def _normalize_metric_key(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _pick_metric_value(numeric_map: Dict[str, float], aliases: tuple[str, ...]) -> float | None:
    if not numeric_map:
        return None

    alias_keys = {_normalize_metric_key(a) for a in aliases if a}
    if not alias_keys:
        return None

    for key, val in numeric_map.items():
        if _normalize_metric_key(key) in alias_keys:
            return float(val)

    for key, val in numeric_map.items():
        normalized_key = _normalize_metric_key(key)
        for alias in alias_keys:
            if normalized_key.endswith(alias):
                return float(val)
    return None


@dataclass
class _Sample:
    ts: datetime
    value: float


class IoTMonitorService:
    def __init__(self) -> None:
        self.host = os.getenv("SUPPORTHUB_MQTT_HOST", "10.206.9.201").strip() or "10.206.9.201"
        self.port = int(os.getenv("SUPPORTHUB_MQTT_PORT", "1883"))
        self.topic = os.getenv("SUPPORTHUB_MQTT_TOPIC", "power/pzem").strip() or "power/pzem1"
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
            "voltage": _pick_metric_value(numeric_map, ("voltage", "volt")),
            "current": _pick_metric_value(numeric_map, ("current", "ampere", "amps")),
            "power": _pick_metric_value(numeric_map, ("power", "watt")),
            "power_factor": _pick_metric_value(numeric_map, ("powerfactor", "pf")),
            "energy": _pick_metric_value(numeric_map, ("energy", "kwh", "wh")),
            "frequency": _pick_metric_value(numeric_map, ("frequency", "freq", "hz")),
            "raw_payload": payload or None,
        }

    def _insert_status_log_row(self, row: Dict[str, Any]) -> None:
        if engine.dialect.name != "postgresql":
            return

        db = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO public.iot_monitor_status_logs (
                        recorded_at,
                        broker,
                        topic,
                        mqtt_client,
                        connected,
                        last_message_at,
                        message_count,
                        parse_error_count,
                        last_payload,
                        last_error
                    )
                    VALUES (
                        :recorded_at,
                        :broker,
                        :topic,
                        :mqtt_client,
                        :connected,
                        :last_message_at,
                        :message_count,
                        :parse_error_count,
                        :last_payload,
                        :last_error
                    )
                    """
                ),
                row,
            )
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[IOT] failed to insert status log: {exc}")
        finally:
            db.close()

    def _insert_measurement_row(self, row: Dict[str, Any]) -> None:
        if engine.dialect.name != "postgresql":
            return

        db = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO public.iot_monitor_measurements (
                        recorded_at,
                        broker,
                        topic,
                        mqtt_client,
                        voltage,
                        current,
                        power,
                        power_factor,
                        energy,
                        frequency,
                        raw_payload
                    )
                    VALUES (
                        :recorded_at,
                        :broker,
                        :topic,
                        :mqtt_client,
                        :voltage,
                        :current,
                        :power,
                        :power_factor,
                        :energy,
                        :frequency,
                        :raw_payload
                    )
                    """
                ),
                row,
            )
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[IOT] failed to insert measurement row: {exc}")
        finally:
            db.close()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
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
            except Exception as exc:
                self.last_error = f"MQTT setup failed: {exc}"

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
                trend_out[key] = [{"ts": _to_iso(s.ts), "value": s.value} for s in q]

            return {
                "broker": f"{self.host}:{self.port}",
                "topic": self.topic,
                "client_id": self.client_id,
                "connected": self.connected,
                "last_error": self.last_error,
                "last_message_at": _to_iso(self.last_message_at),
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
        self._insert_status_log_row(status_row)

    def _on_disconnect(self, client, userdata, reason_code, properties=None):  # noqa: ANN001
        now = datetime.utcnow()
        rc = getattr(reason_code, "value", reason_code)
        status_row: Dict[str, Any]
        with self._lock:
            self.connected = False
            if int(rc) != 0:
                self.last_error = f"MQTT disconnected (reason_code={reason_code})"
            status_row = self._build_status_log_row(now)
        self._insert_status_log_row(status_row)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        try:
            payload = (msg.payload or b"").decode("utf-8", errors="replace").strip()
        except Exception:
            payload = str(msg.payload)

        now = datetime.utcnow()
        numeric_map: Dict[str, float] = {}

        if payload:
            try:
                if payload.startswith("{") or payload.startswith("["):
                    obj = json.loads(payload)
                    numeric_map = _extract_numeric(obj)
                else:
                    num = _safe_float(payload)
                    if num is not None:
                        numeric_map = {"value": num}
            except Exception:
                numeric_map = {}

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
        self._insert_status_log_row(status_row)
        self._insert_measurement_row(measurement_row)


iot_monitor = IoTMonitorService()

