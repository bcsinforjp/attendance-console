DROP VIEW IF EXISTS attendance_dashboard_records;

CREATE VIEW attendance_dashboard_records AS
WITH base AS (
    SELECT
        month_year,
        record_date,
        personal_code,
        full_name,
        NULLIF(commute_time, '') AS commute_time,
        NULLIF(time_to_leave, '') AS time_to_leave,
        NULLIF(working_hours, '') AS working_hours,
        CASE
            WHEN commute_time ~ '^[0-9]+:[0-9]{2}$' THEN
                split_part(commute_time, ':', 1)::int * 60 + split_part(commute_time, ':', 2)::int
            ELSE NULL
        END AS start_minutes,
        CASE
            WHEN time_to_leave ~ '^[0-9]+:[0-9]{2}$' THEN
                split_part(time_to_leave, ':', 1)::int * 60 + split_part(time_to_leave, ':', 2)::int
            ELSE NULL
        END AS leave_minutes_raw,
        CASE
            WHEN regexp_replace(COALESCE(working_hours, ''), '\s*hr$', '') ~ '^[0-9]+:[0-9]{2}$' THEN
                split_part(regexp_replace(COALESCE(working_hours, ''), '\s*hr$', ''), ':', 1)::int * 60 +
                split_part(regexp_replace(COALESCE(working_hours, ''), '\s*hr$', ''), ':', 2)::int
            ELSE NULL
        END AS working_minutes_raw
    FROM attendance_records
),
normalized AS (
    SELECT
        month_year,
        record_date,
        personal_code,
        full_name,
        COALESCE(commute_time, '') AS commute_time,
        COALESCE(time_to_leave, '') AS time_to_leave,
        COALESCE(working_hours, '') AS working_hours,
        start_minutes,
        CASE
            WHEN leave_minutes_raw IS NULL THEN NULL
            WHEN leave_minutes_raw >= 24 * 60 THEN leave_minutes_raw
            WHEN start_minutes IS NOT NULL AND leave_minutes_raw < start_minutes THEN leave_minutes_raw + 24 * 60
            ELSE leave_minutes_raw
        END AS leave_minutes,
        CASE
            WHEN working_minutes_raw IS NOT NULL THEN working_minutes_raw
            WHEN start_minutes IS NOT NULL AND leave_minutes_raw IS NOT NULL THEN
                CASE
                    WHEN leave_minutes_raw >= 24 * 60 THEN leave_minutes_raw - start_minutes
                    WHEN leave_minutes_raw < start_minutes THEN leave_minutes_raw + 24 * 60 - start_minutes
                    ELSE leave_minutes_raw - start_minutes
                END
            ELSE NULL
        END AS working_minutes
    FROM base
)
SELECT
    month_year,
    record_date,
    personal_code,
    full_name,
    commute_time,
    time_to_leave,
    working_hours,
    start_minutes,
    leave_minutes,
    working_minutes,
    (commute_time <> '' OR time_to_leave <> '' OR working_hours <> '') AS has_data,
    (commute_time <> '' AND time_to_leave = '') AS missing_leave,
    (start_minutes > 9 * 60) AS is_late,
    (start_minutes > 10 * 60) AS is_very_late,
    (start_minutes >= 16 * 60) AS is_evening_start,
    (leave_minutes IS NOT NULL AND start_minutes IS NOT NULL AND leave_minutes > 24 * 60) AS is_overnight,
    (working_minutes IS NOT NULL AND working_minutes >= 8 * 60) AS is_overtime,
    (working_minutes IS NOT NULL AND working_minutes >= 10 * 60) AS is_long_shift,
    (working_minutes IS NOT NULL AND working_minutes > 0 AND working_minutes < 4 * 60) AS is_short_shift,
    CASE
        WHEN leave_minutes IS NULL THEN ''
        ELSE lpad((leave_minutes / 60)::text, 2, '0') || ':' || lpad((leave_minutes % 60)::text, 2, '0')
    END AS normalized_leave_time,
    CASE
        WHEN working_minutes IS NULL THEN ''
        ELSE lpad((working_minutes / 60)::text, 2, '0') || ':' || lpad((working_minutes % 60)::text, 2, '0') || ' hr'
    END AS working_hours_label,
    CASE
        WHEN working_minutes IS NULL THEN NULL
        ELSE ROUND(working_minutes / 60.0, 2)
    END AS working_hours_decimal,
    to_char(record_date, 'Dy') AS weekday_name,
    date_trunc('week', record_date)::date AS week_start
FROM normalized;
