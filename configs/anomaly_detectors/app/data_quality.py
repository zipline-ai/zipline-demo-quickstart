from ai.chronon.types import AnomalyAlertPolicy, AnomalyDetector, AnomalyMetric, ApplyDetector

# Use past rolling-origin errors to choose an empirical alert threshold, then
# report its alert rate on a separate later slice. These are unlabeled metrics:
# the budget is one alert per 365 observed days, not a false-positive guarantee.
# Seven prior observations enable broad provisional bounds. Long-term calibration
# remains optional for startup: its evidence is collected without blocking alerts.
# The final seven-day evaluation window is never used to tune the bounds.
sporadic_volume_preview = ApplyDetector(
    AnomalyDetector(
        "volume_alert_budget",
        lookback_days=1095,
        min_history_days=28,
        interval_width=0.95,
        forecast_horizon_days=7,
    ),
    metrics=[
        AnomalyMetric(
            "row_count",
            alert_policy=AnomalyAlertPolicy(
                target_alert_rate=1 / 365,
                min_calibration_points=365,
                validation_points=365,
                min_absolute_change=100,
                min_relative_change=0.25,
            ),
        )
    ],
    targets=[
        "joins/app/client_request_context.client_request_context__3",
        "joins/app/email_activity_profile.email_activity_profile__2",
        "joins/app/user_request_identity.user_request_identity__9",
    ],
)


# Explicit output columns verified from the existing metrics schema.
client_nulls_preview = ApplyDetector(
    AnomalyDetector("nulls_alert_budget", lookback_days=1095),
    targets=['joins/app/client_request_context.client_request_context__3'],
    metrics=[
        AnomalyMetric("null_rate", column=column, alert_policy=AnomalyAlertPolicy(
            target_alert_rate=1 / 365, min_calibration_points=365, validation_points=365,
            min_absolute_change=0.05, min_relative_change=0.25,
        ))
        for column in ['actor_id', 'client_error_event', 'client_ip', 'client_ip_client_error_event_sum_1d', 'client_ip_freshness_lag_seconds_last', 'client_ip_request_count_sum_1d', 'client_ip_request_time_seconds_average_1d', 'client_ip_server_error_event_sum_1d', 'client_ip_success_event_sum_1d', 'client_ip_write_event_sum_1d', 'error_event', 'event_id', 'freshness_lag_seconds', 'freshness_risk', 'http_method', 'path', 'request_count', 'request_time_seconds', 'route_family', 'route_family_client_error_event_sum_1d', 'route_family_freshness_lag_seconds_last', 'route_family_freshness_lag_seconds_max_1d', 'route_family_not_found_event_sum_1d', 'route_family_request_count_sum_1d', 'route_family_request_time_seconds_average_1d', 'route_family_request_time_seconds_max_1d', 'route_family_server_error_event_sum_1d', 'route_family_success_event_sum_1d', 'route_family_write_event_sum_1d', 'server_error_event', 'success_event', 'ts', 'user_agent', 'user_id', 'write_event']
    ],
)


# Explicit output columns verified from the existing metrics schema.
email_nulls_preview = ApplyDetector(
    AnomalyDetector("nulls_alert_budget", lookback_days=1095),
    targets=['joins/app/email_activity_profile.email_activity_profile__2'],
    metrics=[
        AnomalyMetric("null_rate", column=column, alert_policy=AnomalyAlertPolicy(
            target_alert_rate=1 / 365, min_calibration_points=365, validation_points=365,
            min_absolute_change=0.05, min_relative_change=0.25,
        ))
        for column in ['email_hash', 'first_seen_ts', 'is_returning_user', 'last_event', 'last_seen_time_iso', 'last_seen_ts', 'user_id_suffix']
    ],
)


# Explicit output columns verified from the existing metrics schema.
identity_nulls_preview = ApplyDetector(
    AnomalyDetector("nulls_alert_budget", lookback_days=1095),
    targets=['joins/app/user_request_identity.user_request_identity__9'],
    metrics=[
        AnomalyMetric("null_rate", column=column, alert_policy=AnomalyAlertPolicy(
            target_alert_rate=1 / 365, min_calibration_points=365, validation_points=365,
            min_absolute_change=0.05, min_relative_change=0.25,
        ))
        for column in ['actor_id', 'client_error_event', 'client_ip', 'error_event', 'event_id', 'freshness_lag_seconds', 'has_authenticated_identity', 'http_method', 'identity_user_id_email_hash', 'identity_user_id_first_seen_ts', 'identity_user_id_last_event', 'identity_user_id_last_seen_time_iso', 'identity_user_id_last_seen_ts', 'path', 'request_count', 'request_time_seconds', 'route_family', 'server_error_event', 'success_event', 'ts', 'user_agent', 'user_id', 'write_event']
    ],
)
