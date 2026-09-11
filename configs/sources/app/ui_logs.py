from ai.chronon.types import EventSource, Query, selects


access_logs = EventSource(
    table="public_demo_app.ui_access_logs_iceberg",
    query=Query(
        selects=selects(
            "event_id",
            "route_family",
            "http_method",
            "path",
            request_count="1",
            error_event="IF(is_error = 1, 1, 0)",
            not_found_event="IF(is_not_found = 1, 1, 0)",
            write_event="IF(is_write = 1, 1, 0)",
            success_event="IF(status_code >= 200 AND status_code < 300, 1, 0)",
            client_error_event="IF(status_code >= 400 AND status_code < 500, 1, 0)",
            server_error_event="IF(status_code >= 500, 1, 0)",
            request_time_seconds="request_time_seconds",
            freshness_lag_seconds="freshness_lag_seconds",
            access_event_struct=(
                "STRUCT(http_method, path, status_code, request_time_seconds, "
                "freshness_lag_seconds, event_ts as timestamp)"
            ),
        ),
        time_column="event_ts",
        partition_column="ds",
        start_partition="2026-09-02",
    ),
)


client_access_logs = EventSource(
    table="public_demo_app.ui_access_logs_iceberg",
    query=Query(
        selects=selects(
            "event_id",
            "route_family",
            "http_method",
            "path",
            "client_ip",
            "user_id",
            "user_agent",
            actor_id="IF(user_id IS NOT NULL AND user_id != '', user_id, client_ip)",
            request_count="1",
            error_event="IF(is_error = 1, 1, 0)",
            write_event="IF(is_write = 1, 1, 0)",
            success_event="IF(status_code >= 200 AND status_code < 300, 1, 0)",
            client_error_event="IF(status_code >= 400 AND status_code < 500, 1, 0)",
            server_error_event="IF(status_code >= 500, 1, 0)",
            request_time_seconds="request_time_seconds",
            freshness_lag_seconds="freshness_lag_seconds",
            access_event_struct=(
                "STRUCT(client_ip, user_id, http_method, path, user_agent, status_code, "
                "request_time_seconds, freshness_lag_seconds, event_ts as timestamp)"
            ),
        ),
        time_column="event_ts",
        partition_column="ds",
        start_partition="2026-09-02",
    ),
)


email_access_logs = EventSource(
    table="public_demo_app.ui_access_logs_iceberg",
    topic=(
        "kinesis://public-demo-ui-access-events/"
        "serde=glue_registry/"
        "registry_name=zipline-public-demo/"
        "schema_name=ui-access-event-v1"
    ),
    query=Query(
        selects=selects(
            "event_id",
            "route_family",
            "http_method",
            "path",
            "client_ip",
            "user_agent",
            visit_ts="event_ts",
            email_hash="substring(sha2(lower(trim(user_id)), 256), 1, 8)",
            request_count="1",
            error_event="IF(is_error = 1, 1, 0)",
            write_event="IF(is_write = 1, 1, 0)",
            freshness_lag_seconds="freshness_lag_seconds",
            activity_event=(
                "STRUCT(client_ip, user_agent, http_method, path, route_family, "
                "is_error as error_event, is_write as write_event, event_ts as timestamp)"
            ),
        ),
        wheres=["user_id IS NOT NULL AND trim(user_id) != ''"],
        time_column="event_ts",
        partition_column="ds",
        start_partition="2026-09-02",
    ),
)
