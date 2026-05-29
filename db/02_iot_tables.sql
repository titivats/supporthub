-- SupportHub IoT monitor tables (MQTT power telemetry).

CREATE TABLE IF NOT EXISTS public.iot_monitor_measurements (
    id           BIGSERIAL PRIMARY KEY,
    recorded_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    broker       VARCHAR(255),
    topic        VARCHAR(255),
    mqtt_client  VARCHAR(255),
    voltage      NUMERIC(14,4),
    current      NUMERIC(14,4),
    power        NUMERIC(14,4),
    power_factor NUMERIC(8,4),
    energy       NUMERIC(18,6),
    frequency    NUMERIC(10,4),
    raw_payload  TEXT,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_iot_power_factor_range
        CHECK (power_factor IS NULL OR (power_factor >= -1 AND power_factor <= 1))
);

CREATE INDEX IF NOT EXISTS idx_iot_monitor_measurements_recorded_at
    ON public.iot_monitor_measurements (recorded_at DESC);

CREATE TABLE IF NOT EXISTS public.iot_monitor_status_logs (
    id                BIGSERIAL PRIMARY KEY,
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    broker            VARCHAR(255),
    topic             VARCHAR(255),
    mqtt_client       VARCHAR(255),
    connected         BOOLEAN     NOT NULL DEFAULT FALSE,
    last_message_at   TIMESTAMPTZ,
    message_count     BIGINT      NOT NULL DEFAULT 0,
    parse_error_count BIGINT      NOT NULL DEFAULT 0,
    last_payload      TEXT,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_iot_monitor_status_logs_recorded_at
    ON public.iot_monitor_status_logs (recorded_at DESC);
