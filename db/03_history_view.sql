-- SupportHub history view: formatted ticket log in Thai time (UTC+7).

DROP VIEW IF EXISTS public.v_history_log;
CREATE VIEW public.v_history_log AS
WITH takeover AS (
    SELECT
        l.ticket_id,
        string_agg(
            to_char(l.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS')
            || ' | ' || coalesce(l.from_actor, '-')
            || ' -> ' || coalesce(l.to_actor, '-'),
            E'\n'
            ORDER BY l.created_at, l.id
        ) AS takeover_log
    FROM ticket_takeover_logs l
    GROUP BY l.ticket_id
),
brand_map AS (
    SELECT lower(mt.machine_type) AS key_name, min(mt.machine) AS machine_name
    FROM master_machine_types mt
    GROUP BY lower(mt.machine_type)
),
machine_map AS (
    SELECT lower(mt.machine) AS key_name, min(mt.machine) AS machine_name
    FROM master_machine_types mt
    GROUP BY lower(mt.machine)
)
SELECT
    t.id AS "ID",
    t.status AS "Status",
    to_char(t.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created (TH)",
    CASE
        WHEN t.closed_at IS NULL THEN '-'
        ELSE to_char(t.closed_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS')
    END AS "Closed (TH)",
    t.requester AS "Request by",
    t.machine AS "Line No.",
    CASE
        WHEN position('||' in coalesce(t.equipment, '')) > 0
            THEN nullif(trim(split_part(t.equipment, '||', 1)), '')
        WHEN lower(coalesce(t.equipment, '')) = 'other m/c or tools'
            THEN 'Etc..'
        ELSE coalesce(mm.machine_name, bm.machine_name, '')
    END AS "Machine",
    CASE
        WHEN position('||' in coalesce(t.equipment, '')) > 0
            THEN nullif(trim(split_part(t.equipment, '||', 2)), '')
        ELSE coalesce(nullif(trim(t.equipment), ''), '')
    END AS "Machine Type",
    coalesce(t.machine_id, '-') AS "Machine ID",
    coalesce(t.problem, '') AS "Problem",
    coalesce(t.description, '-') AS "Description",
    lpad((dur.doing_secs / 3600)::text, 2, '0') || ':' ||
    lpad(((mod(dur.doing_secs, 3600)) / 60)::text, 2, '0') || ':' ||
    lpad((mod(dur.doing_secs, 60))::text, 2, '0') AS "Doing",
    lpad((dur.hold_secs / 3600)::text, 2, '0') || ':' ||
    lpad(((mod(dur.hold_secs, 3600)) / 60)::text, 2, '0') || ':' ||
    lpad((mod(dur.hold_secs, 60))::text, 2, '0') AS "Hold",
    coalesce(t.hold_reason, '-') AS "Hold Reason",
    lpad((dur.wait_secs / 3600)::text, 2, '0') || ':' ||
    lpad(((mod(dur.wait_secs, 3600)) / 60)::text, 2, '0') || ':' ||
    lpad((mod(dur.wait_secs, 60))::text, 2, '0') AS "Waiting Time",
    lpad((dur.sum_secs / 3600)::text, 2, '0') || ':' ||
    lpad(((mod(dur.sum_secs, 3600)) / 60)::text, 2, '0') || ':' ||
    lpad((mod(dur.sum_secs, 60))::text, 2, '0') AS "Downtime",
    coalesce(t.solution, '-') AS "Solution",
    coalesce(t.cancel_reason, '-') AS "Cancel Reason",
    coalesce(tk.takeover_log, '-') AS "Takeover Log",
    CASE
        WHEN t.status = 'DONE' THEN coalesce(t.done_by, '-')
        WHEN t.status = 'CANCELLED' THEN coalesce(t.canceled_by, '-')
        ELSE '-'
    END AS "Done By"
FROM tickets t
LEFT JOIN brand_map bm
    ON bm.key_name = lower(coalesce(t.equipment, ''))
LEFT JOIN machine_map mm
    ON mm.key_name = lower(coalesce(t.equipment, ''))
LEFT JOIN takeover tk
    ON tk.ticket_id = t.id
LEFT JOIN LATERAL (
    SELECT
        greatest(coalesce(t.doing_secs, 0), 0) AS doing_secs,
        greatest(coalesce(t.hold_secs, 0), 0) AS hold_secs,
        greatest(
            coalesce(extract(epoch FROM (coalesce(t.closed_at, t.created_at) - t.created_at))::int, 0),
            0
        ) AS sum_secs,
        greatest(
            coalesce(extract(epoch FROM (coalesce(t.closed_at, t.created_at) - t.created_at))::int, 0)
            - greatest(coalesce(t.doing_secs, 0), 0)
            - greatest(coalesce(t.hold_secs, 0), 0),
            0
        ) AS wait_secs
) dur ON true
ORDER BY t.id DESC;
