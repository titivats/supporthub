-- SupportHub core schema (mirrors SQLAlchemy models in python/database/core.py)
-- PostgreSQL only.

CREATE TABLE IF NOT EXISTS public.users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    role          VARCHAR(20)  NOT NULL,
    created_at    TIMESTAMP    DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_username UNIQUE (username)
);

CREATE TABLE IF NOT EXISTS public.tickets (
    id               SERIAL PRIMARY KEY,
    created_at       TIMESTAMP    DEFAULT (now() AT TIME ZONE 'utc'),
    closed_at        TIMESTAMP,
    requester        VARCHAR(50)  NOT NULL,
    machine          VARCHAR(50),
    equipment        VARCHAR(200),
    machine_id       VARCHAR(100),
    problem          VARCHAR(100),
    description      TEXT,
    status           VARCHAR(12)  NOT NULL DEFAULT 'PENDING',
    doing_started_at TIMESTAMP,
    hold_started_at  TIMESTAMP,
    doing_secs       INTEGER      NOT NULL DEFAULT 0,
    hold_secs        INTEGER      NOT NULL DEFAULT 0,
    current_actor    VARCHAR(50),
    last_action      VARCHAR(10),
    hold_reason      TEXT,
    solution         TEXT,
    done_by          VARCHAR(50),
    cancel_reason    TEXT,
    canceled_by      VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON public.tickets (created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_status     ON public.tickets (status);
CREATE INDEX IF NOT EXISTS idx_tickets_closed_at  ON public.tickets (closed_at);
CREATE INDEX IF NOT EXISTS idx_tickets_machine    ON public.tickets (machine);
CREATE INDEX IF NOT EXISTS idx_tickets_machine_id ON public.tickets (machine_id);

CREATE TABLE IF NOT EXISTS public.ticket_takeover_logs (
    id         SERIAL PRIMARY KEY,
    ticket_id  INTEGER     NOT NULL,
    from_actor VARCHAR(50),
    to_actor   VARCHAR(50) NOT NULL,
    status     VARCHAR(12) NOT NULL,
    created_at TIMESTAMP   NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_takeover_ticket_id  ON public.ticket_takeover_logs (ticket_id);
CREATE INDEX IF NOT EXISTS idx_takeover_created_at ON public.ticket_takeover_logs (created_at);

CREATE TABLE IF NOT EXISTS public.master_lines (
    id         SERIAL PRIMARY KEY,
    line_no    VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP   NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS public.master_machines (
    id         SERIAL PRIMARY KEY,
    machine    VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS public.master_machine_types (
    id           SERIAL PRIMARY KEY,
    machine      VARCHAR(100) NOT NULL,
    machine_type VARCHAR(100) NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_master_machine_type UNIQUE (machine, machine_type)
);

CREATE INDEX IF NOT EXISTS idx_mmt_machine      ON public.master_machine_types (machine);
CREATE INDEX IF NOT EXISTS idx_mmt_machine_type ON public.master_machine_types (machine_type);

CREATE TABLE IF NOT EXISTS public.master_problems (
    id           SERIAL PRIMARY KEY,
    machine      VARCHAR(100) NOT NULL,
    machine_type VARCHAR(100),
    problem      VARCHAR(150) NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_master_problem UNIQUE (machine, machine_type, problem)
);

CREATE INDEX IF NOT EXISTS idx_mp_machine      ON public.master_problems (machine);
CREATE INDEX IF NOT EXISTS idx_mp_machine_type ON public.master_problems (machine_type);

CREATE TABLE IF NOT EXISTS public.master_machine_ids (
    id           SERIAL PRIMARY KEY,
    machine      VARCHAR(100) NOT NULL,
    machine_type VARCHAR(100) NOT NULL,
    machine_id   VARCHAR(100) NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_master_machine_id UNIQUE (machine, machine_type, machine_id)
);

CREATE INDEX IF NOT EXISTS idx_mmi_machine      ON public.master_machine_ids (machine);
CREATE INDEX IF NOT EXISTS idx_mmi_machine_type ON public.master_machine_ids (machine_type);

CREATE TABLE IF NOT EXISTS public.master_support_areas (
    id           SERIAL PRIMARY KEY,
    support_area VARCHAR(100) NOT NULL UNIQUE,
    created_at   TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS public.master_support_area_maps (
    id           SERIAL PRIMARY KEY,
    support_area VARCHAR(100) NOT NULL,
    machine      VARCHAR(100) NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_master_support_area_machine UNIQUE (support_area, machine)
);

CREATE INDEX IF NOT EXISTS idx_msam_support_area ON public.master_support_area_maps (support_area);
CREATE INDEX IF NOT EXISTS idx_msam_machine      ON public.master_support_area_maps (machine);

CREATE TABLE IF NOT EXISTS public.app_settings (
    id         SERIAL PRIMARY KEY,
    key        VARCHAR(100) NOT NULL UNIQUE,
    value      VARCHAR(200) NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS public.master_audit_logs (
    id         SERIAL PRIMARY KEY,
    action     VARCHAR(20)  NOT NULL,
    data_type  VARCHAR(50)  NOT NULL,
    item       VARCHAR(250) NOT NULL,
    actor      VARCHAR(50)  NOT NULL,
    details    TEXT,
    created_at TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_mal_action     ON public.master_audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_mal_data_type  ON public.master_audit_logs (data_type);
CREATE INDEX IF NOT EXISTS idx_mal_actor      ON public.master_audit_logs (actor);
CREATE INDEX IF NOT EXISTS idx_mal_created_at ON public.master_audit_logs (created_at);
