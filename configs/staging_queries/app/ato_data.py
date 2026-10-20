"""Simulated account-takeover (ATO) traffic layered on real demo access logs.

The public demo has no fraud outcomes, so these staging queries build a labelled
ATO scenario without adding any new input tables:

* ``activity`` keeps every real request from ``ui_access_logs_iceberg`` and adds
  synthetic sessions to established account-days. The demo has only a few
  dozen organic sessions a day, so each account-day gets several independent
  injection slots to yield enough labelled attacks to train and validate on. Two kinds are attacks (scripted credential stuffing from a shared
  hosting pool, and stealthy takeovers that spoof the victim's browser from a
  residential IP). Two kinds are benign look-alikes (a new personal device, and a
  login through a shared VPN egress) so that "new IP" or "shared IP" alone is not
  a perfect signal.
* ``sessions`` rolls activity into account/IP/user-agent/hour sessions and labels
  each one. Only 85% of attacks are confirmed, mirroring victims who never report.

Everything is derived with XXHASH64 over stable keys, so reruns and differently
chunked backfills produce identical rows. Accounts are the authenticated
``user_id``; anonymous traffic is keyed by its client IP as ``ip:<address>``.
``scenario`` is simulation ground truth for slicing results. Feature sources must
never select it.
"""

from ai.chronon.types import ConfigProperties, EngineType, StagingQuery, TableDependency

_LOGS = "public_demo_app.ui_access_logs_iceberg"

# An account-day is eligible only if the account was active in the prior 14 days,
# so attacks land on established accounts instead of first-time visitors.
_LOOKBACK_DAYS = 14

# Independent injection slots per eligible account-day.
_SLOTS = 12

# Scenario buckets out of 1000 per slot.
_ATO_SCRIPTED = 30  # 3.0%
_ATO_STEALTH = 60  # +3.0%
_NEW_DEVICE = 105  # +4.5%
_VPN_NEW_DEVICE = 130  # +2.5%

# Share of attack sessions that receive a confirmed fraud label.
_CONFIRMED_PERCENT = 85

_SCRIPTED_AGENTS = [
    "python-requests/2.32.3",
    "curl/8.7.1",
    "Go-http-client/1.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

_PERSONAL_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
]

_WRITE_PATHS = ["/api/tokens", "/api/users/me/email", "/api/users/me/mfa", "/api/settings/webhooks"]
_READ_PATHS = ["/", "/workflows", "/services/hub/api/confs", "/services/hub/api/users/me"]


def _hash(salt, buckets, *keys):
    columns = ", ".join(keys or ("account_id", "ds", "slot"))
    return f"CAST(PMOD(XXHASH64({columns}, '{salt}'), {buckets}) AS INT)"


def _pick(values, salt, *keys):
    items = ", ".join(str(v) if isinstance(v, int) else f"'{v}'" for v in values)
    return f"ELEMENT_AT(ARRAY({items}), 1 + {_hash(salt, len(values), *keys)})"


_DAY_START_MS = "UNIX_TIMESTAMP(TO_TIMESTAMP(ds, 'yyyy-MM-dd')) * 1000"
_STEP_KEYS = ("account_id", "ds", "slot", "step")

activity = StagingQuery(
    query=f"""
WITH raw AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ingested_at) AS copy_number
    FROM {_LOGS}
    WHERE ds BETWEEN DATE_FORMAT(DATE_SUB(TO_DATE({{{{ start_date }}}}), {_LOOKBACK_DAYS}), 'yyyy-MM-dd')
                 AND {{{{ end_date }}}}
),
organic AS (
    SELECT
        event_id,
        COALESCE(NULLIF(TRIM(user_id), ''), CONCAT('ip:', client_ip)) AS account_id,
        client_ip,
        COALESCE(NULLIF(TRIM(user_agent), ''), 'unknown') AS user_agent,
        http_method,
        path,
        status_code,
        event_ts,
        ds
    FROM raw
    WHERE copy_number = 1 AND client_ip IS NOT NULL AND client_ip != ''
),
account_days AS (
    SELECT account_id, ds, MAX_BY(user_agent, event_ts) AS usual_user_agent
    FROM organic
    GROUP BY account_id, ds
),
established AS (
    SELECT d.account_id, d.ds, d.usual_user_agent
    FROM account_days d
    LEFT SEMI JOIN account_days p
      ON p.account_id = d.account_id
     AND TO_DATE(p.ds) BETWEEN DATE_SUB(TO_DATE(d.ds), {_LOOKBACK_DAYS})
                           AND DATE_SUB(TO_DATE(d.ds), 1)
    WHERE d.ds BETWEEN {{{{ start_date }}}} AND {{{{ end_date }}}}
),
slots AS (
    SELECT e.*, slot
    FROM established e
    LATERAL VIEW EXPLODE(SEQUENCE(1, {_SLOTS})) s AS slot
),
scenarios AS (
    SELECT
        account_id,
        ds,
        slot,
        usual_user_agent,
        CASE
            WHEN bucket < {_ATO_SCRIPTED} THEN 'ato_scripted'
            WHEN bucket < {_ATO_STEALTH} THEN 'ato_stealth'
            WHEN bucket < {_NEW_DEVICE} THEN 'new_device'
            ELSE 'vpn_new_device'
        END AS scenario
    FROM (SELECT *, {_hash('scenario', 1000)} AS bucket FROM slots) e
    WHERE bucket < {_VPN_NEW_DEVICE}
),
plans AS (
    SELECT
        account_id,
        ds,
        slot,
        scenario,
        CASE scenario
            -- Credential-stuffing infrastructure: 48 hosting IPs reused across victims.
            WHEN 'ato_scripted' THEN CONCAT('185.220.', 100 + {_hash('subnet', 4)}, '.', 10 + {_hash('host', 12)})
            -- Residential proxies and home networks: effectively unique per session.
            WHEN 'ato_stealth' THEN CONCAT('98.', {_hash('o2', 256)}, '.', {_hash('o3', 256)}, '.', 1 + {_hash('o4', 254)})
            WHEN 'new_device' THEN CONCAT('73.', {_hash('o2', 256)}, '.', {_hash('o3', 256)}, '.', 1 + {_hash('o4', 254)})
            -- Commercial VPN egress: 40 IPs legitimately shared by many accounts.
            ELSE CONCAT('104.28.', 30 + {_hash('subnet', 2)}, '.', 10 + {_hash('host', 20)})
        END AS client_ip,
        CASE scenario
            WHEN 'ato_scripted' THEN {_pick(_SCRIPTED_AGENTS, 'agent')}
            WHEN 'ato_stealth' THEN usual_user_agent
            ELSE {_pick(_PERSONAL_AGENTS, 'agent')}
        END AS user_agent,
        CASE scenario
            WHEN 'ato_scripted' THEN {_pick([0, 1, 2, 3, 4, 5, 22, 23, 13, 17], 'hour')}
            WHEN 'ato_stealth' THEN 14 + {_hash('hour', 8)}
            -- One in five new devices is someone travelling, active overnight UTC.
            WHEN 'new_device' THEN IF({_hash('travel', 5)} = 0, {_hash('hour', 6)}, 14 + {_hash('hour', 9)})
            ELSE 14 + {_hash('hour', 9)}
        END AS start_hour,
        {_hash('minute', 45)} AS start_minute,
        CASE scenario
            -- One in eight scripted attacks already holds a valid password.
            WHEN 'ato_scripted' THEN {_hash('failures', 8)}
            ELSE IF({_hash('failures', 4)} = 0, 1, 0)
        END AS failed_logins,
        CASE scenario
            WHEN 'ato_scripted' THEN 6 + {_hash('actions', 20)}
            ELSE 3 + {_hash('actions', 12)}
        END AS actions,
        CASE scenario WHEN 'ato_scripted' THEN 45 WHEN 'ato_stealth' THEN 15 ELSE 8 END AS write_percent,
        -- Milliseconds between requests: scripted attacks move at machine speed.
        CASE scenario
            WHEN 'ato_scripted' THEN 1500 + {_hash('pace', 2500)}
            ELSE 15000 + {_hash('pace', 45000)}
        END AS step_ms
    FROM scenarios
),
steps AS (
    SELECT
        p.*,
        step,
        step <= failed_logins + 1 AS is_login,
        {_hash('write', 100, *_STEP_KEYS)} < write_percent AS is_write
    FROM plans p
    LATERAL VIEW EXPLODE(SEQUENCE(1, failed_logins + 1 + actions)) s AS step
),
injected AS (
    SELECT
        SHA2(CONCAT_WS('|', 'simulated', account_id, ds, CAST(slot AS STRING), CAST(step AS STRING)), 256)
            AS event_id,
        account_id,
        client_ip,
        user_agent,
        CASE
            WHEN is_login THEN 'POST'
            WHEN is_write THEN {_pick(['POST', 'PUT', 'DELETE'], 'method', *_STEP_KEYS)}
            ELSE 'GET'
        END AS http_method,
        CASE
            WHEN is_login THEN '/api/auth/login'
            WHEN is_write THEN {_pick(_WRITE_PATHS, 'path', *_STEP_KEYS)}
            ELSE {_pick(_READ_PATHS, 'path', *_STEP_KEYS)}
        END AS path,
        IF(step <= failed_logins, 401, 200) AS status_code,
        {_DAY_START_MS} + start_hour * 3600000 + start_minute * 60000 + step * step_ms AS event_ts,
        CONCAT('simulated:', account_id, ':', ds, ':', slot) AS session_id,
        scenario,
        ds
    FROM steps
)
SELECT
    event_id,
    account_id,
    client_ip,
    user_agent,
    http_method,
    path,
    status_code,
    event_ts,
    SHA2(CONCAT_WS('|', account_id, client_ip, user_agent, CAST(FLOOR(event_ts / 3600000) AS STRING)), 256)
        AS session_id,
    'organic' AS scenario,
    ds
FROM organic
WHERE ds BETWEEN {{{{ start_date }}}} AND {{{{ end_date }}}}
UNION ALL
SELECT
    event_id,
    account_id,
    client_ip,
    user_agent,
    http_method,
    path,
    status_code,
    event_ts,
    session_id,
    scenario,
    ds
FROM injected
""",
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    offline_schedule="@never",
    # The query also reads a 14-day lookback for eligibility. It is not declared,
    # because the access logs start on 2026-09-02 and earlier partitions never land.
    dependencies=[
        TableDependency(table=_LOGS, partition_column="ds", start_offset=0, end_offset=0),
    ],
    step_days=14,
    version=2,
)

sessions = StagingQuery(
    query=f"""
SELECT
    session_id,
    account_id,
    client_ip,
    user_agent,
    MIN(event_ts) AS session_start_ts,
    MAX(event_ts) AS session_end_ts,
    COUNT(*) AS session_requests,
    MAX(scenario) AS scenario,
    CAST(
        MAX(scenario) IN ('ato_scripted', 'ato_stealth')
        AND {_hash('confirmed', 100, 'session_id')} < {_CONFIRMED_PERCENT}
        AS INT
    ) AS is_ato,
    ds
FROM {activity.table}
WHERE ds BETWEEN {{{{ start_date }}}} AND {{{{ end_date }}}}
GROUP BY session_id, account_id, client_ip, user_agent, ds
""",
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    offline_schedule="@never",
    dependencies=[
        TableDependency(table=activity.table, partition_column="ds", start_offset=0, end_offset=0),
    ],
    step_days=14,
    version=2,
)
