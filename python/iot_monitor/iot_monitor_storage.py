from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text

from python.database import SessionLocal, engine


def insert_status_log_row(row: Dict[str, Any]) -> None:
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


def insert_measurement_row(row: Dict[str, Any]) -> None:
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
