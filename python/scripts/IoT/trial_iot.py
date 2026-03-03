from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import paho.mqtt.client as mqtt

try:
    from influxdb_client import InfluxDBClient  # optional
except Exception:
    InfluxDBClient = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MQTT subscriber and InfluxDB forwarder")
    parser.add_argument(
        "--mode",
        default="subscribe",
        choices=["subscribe", "influx-forward"],
        help="subscribe: listen to MQTT topic, influx-forward: read from InfluxDB and publish to MQTT",
    )
    parser.add_argument("--host", default="192.168.1.109", help="MQTT host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT port")
    parser.add_argument("--topic", default="power/pzem", help="MQTT subscribe topic")
    parser.add_argument("--client-id", default="TESTIOT", help="MQTT client id for subscribe mode")
    parser.add_argument("--publish-topic", default="tesla-supporthub", help="MQTT publish topic for influx-forward mode")
    parser.add_argument("--publish-client-id", default="TESTIOT-FWD", help="MQTT client id for influx-forward mode")

    parser.add_argument("--influx-url", default="", help="InfluxDB URL, example http://localhost:8086")
    parser.add_argument("--influx-token", default="", help="InfluxDB token")
    parser.add_argument("--influx-org", default="", help="InfluxDB org")
    parser.add_argument("--influx-bucket", default="", help="InfluxDB bucket")
    parser.add_argument("--influx-measurement", default="", help="Influx measurement filter")
    parser.add_argument("--influx-field", default="", help="Influx field filter")
    parser.add_argument("--influx-range", default="-2m", help="Flux range start, example -10m")
    parser.add_argument("--poll-seconds", type=int, default=5, help="Influx poll interval in seconds")
    return parser


def run_subscribe(args: argparse.Namespace) -> int:
    def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
        if int(reason_code) == 0:
            print(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] Connected")
            client.subscribe(args.topic, qos=0)
            print(f"Subscribed topic: {args.topic}")
        else:
            print(f"MQTT connect failed (reason_code={reason_code})")

    def on_message(client, userdata, msg):  # noqa: ANN001
        payload = (msg.payload or b"").decode("utf-8", errors="replace").strip()
        print(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] {msg.topic} -> {payload}")

    try:
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=args.client_id,
                protocol=mqtt.MQTTv311,
            )
        except Exception:
            client = mqtt.Client(client_id=args.client_id, protocol=mqtt.MQTTv311)

        client.on_connect = on_connect
        client.on_message = on_message

        print(f"Connecting mqtt://{args.host}:{args.port}")
        client.connect(args.host, args.port, keepalive=30)
        client.loop_forever()
        return 0
    except KeyboardInterrupt:
        print("\nStopped by user")
        return 0
    except Exception as exc:
        print(f"Subscribe failed: {exc}")
        return 1


def _build_flux_query(args: argparse.Namespace) -> str:
    lines = [
        f'from(bucket: "{args.influx_bucket}")',
        f"  |> range(start: {args.influx_range})",
    ]
    if args.influx_measurement:
        lines.append(f'  |> filter(fn: (r) => r["_measurement"] == "{args.influx_measurement}")')
    if args.influx_field:
        lines.append(f'  |> filter(fn: (r) => r["_field"] == "{args.influx_field}")')
    lines.append("  |> last()")
    return "\n".join(lines)


def run_influx_forward(args: argparse.Namespace) -> int:
    if InfluxDBClient is None:
        print("Missing dependency: influxdb-client (pip install influxdb-client)")
        return 1

    required = {
        "influx-url": args.influx_url.strip(),
        "influx-token": args.influx_token.strip(),
        "influx-org": args.influx_org.strip(),
        "influx-bucket": args.influx_bucket.strip(),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"Missing required args for influx-forward: {', '.join(missing)}")
        return 1

    try:
        try:
            pub_client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=args.publish_client_id,
                protocol=mqtt.MQTTv311,
            )
        except Exception:
            pub_client = mqtt.Client(client_id=args.publish_client_id, protocol=mqtt.MQTTv311)

        pub_client.connect(args.host, args.port, keepalive=30)
        pub_client.loop_start()

        flux_query = _build_flux_query(args)
        print("Starting InfluxDB forwarder")
        print(f"Influx URL: {args.influx_url}")
        print(f"Influx bucket: {args.influx_bucket}")
        print(f"Publish MQTT: {args.host}:{args.port} topic={args.publish_topic}")

        with InfluxDBClient(url=args.influx_url, token=args.influx_token, org=args.influx_org) as influx_client:
            query_api = influx_client.query_api()
            while True:
                try:
                    tables = query_api.query(org=args.influx_org, query=flux_query)
                    payloads = []
                    for table in tables:
                        for record in table.records:
                            payloads.append({
                                "measurement": record.get_measurement(),
                                "field": record.get_field(),
                                "value": record.get_value(),
                                "time": record.get_time().isoformat() if record.get_time() else None,
                            })

                    if payloads:
                        out = json.dumps(payloads[0] if len(payloads) == 1 else payloads, ensure_ascii=False)
                        pub_client.publish(args.publish_topic, out, qos=0, retain=False)
                        print(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] Published: {out}")
                    else:
                        print(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] No influx result")
                except Exception as exc:
                    print(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] Query error: {exc}")
                time.sleep(max(args.poll_seconds, 1))
    except KeyboardInterrupt:
        print("\nStopping influx forwarder")
        return 0
    except Exception as exc:
        print(f"Forwarder failed: {exc}")
        return 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "influx-forward":
        return run_influx_forward(args)
    return run_subscribe(args)


if __name__ == "__main__":
    raise SystemExit(main())

