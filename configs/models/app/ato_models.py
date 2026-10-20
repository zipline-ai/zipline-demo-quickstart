"""Account-takeover trial: a rules baseline against three XGBoost feature sets.

Every variant uses the demo's shared Ray/XGBoost trainer, the same training rows,
and the same date holdout, so only the inputs differ:

* ``ato_rules_baseline``: only ``rule_score``, the count of four hand-written
  rules that fire. With depth-1 trees the trainer just calibrates that score, so
  its metrics measure the rules themselves.
* ``ato_xgb_velocity``: per-account request, write, and auth-failure velocity.
* ``ato_xgb_novelty``: adds IP and device novelty plus session context.
* ``ato_xgb_full``: adds IP reputation across accounts and the rule flags.

Artifacts live under the warehouse bucket, which both the Ray trainer and Hub
can read, so Hub can attach the trainer's report to a trial. Each model name
needs a trainer archive at ``<_ARTIFACTS>/builds/<model_name>-2.zip``;
see docs/ato.md.
"""

from joins.app import ato_training
from teams import WAREHOUSE_PREFIX

from ai.chronon.types import (
    DataType,
    EventSource,
    InferenceSpec,
    Model,
    ModelBackend,
    Query,
    ResourceConfig,
    TimeUnit,
    TrainingSpec,
    Window,
    selects,
)

# The shared demo trainer, build 19ca8c1c152c, copied per model name. The model
# version starts at 2 because version 19ca8c1c152c first wrote to the artifacts
# bucket; Hub resolves a model conf by name, so each name keeps one location.
_MODEL_VERSION = "2"
_ARTIFACTS = f"{WAREHOUSE_PREFIX}/ato_models"

# The access logs start on 2026-09-02; a week of warm-up precedes the first row.
_TRAIN_START = "2026-09-09"
_TRAIN_END = "2026-10-18"

_RULES = [("rule_score", "rule_score")]

_VELOCITY = [
    ("account_id_request_count_sum_1h", "requests_1h"),
    ("account_id_request_count_sum_1d", "requests_1d"),
    ("account_id_request_count_sum_7d", "requests_7d"),
    ("account_id_write_event_sum_1h", "writes_1h"),
    ("account_id_write_event_sum_1d", "writes_1d"),
    ("account_id_write_event_sum_7d", "writes_7d"),
    ("account_id_auth_failure_event_sum_1h", "auth_failures_1h"),
    ("account_id_auth_failure_event_sum_1d", "auth_failures_1d"),
    ("account_id_auth_failure_event_sum_7d", "auth_failures_7d"),
    ("account_id_client_ip_approx_unique_count_1d", "distinct_ips_1d"),
    ("account_id_client_ip_approx_unique_count_7d", "distinct_ips_7d"),
    ("account_id_user_agent_approx_unique_count_1d", "distinct_agents_1d"),
    ("account_id_user_agent_approx_unique_count_7d", "distinct_agents_7d"),
]

_NOVELTY = _VELOCITY + [
    ("hours_since_ip_first_seen", "ip_age_hours"),
    ("hours_since_agent_first_seen", "agent_age_hours"),
    ("account_id_client_ip_request_count_sum_14d", "ip_requests_14d"),
    ("account_id_user_agent_request_count_sum_14d", "agent_requests_14d"),
    ("account_age_hours", "account_age_hours"),
    ("prior_account_requests_7d", "prior_requests_7d"),
    ("session_write_share", "session_write_share"),
    ("session_requests_per_minute", "session_request_rate"),
    ("session_hour_utc", "session_hour_utc"),
    ("is_automation_agent", "automation_agent"),
]

_FULL = _NOVELTY + [
    ("client_ip_account_id_approx_unique_count_1d", "ip_accounts_1d"),
    ("client_ip_account_id_approx_unique_count_7d", "ip_accounts_7d"),
    ("client_ip_auth_failure_event_sum_1d", "ip_auth_failures_1d"),
    ("client_ip_auth_failure_event_sum_7d", "ip_auth_failures_7d"),
    ("client_ip_request_count_sum_1d", "ip_requests_1d"),
    ("rule_new_ip_and_device", "rule_new_ip_and_device"),
    ("rule_auth_failures", "rule_auth_failures"),
    ("rule_scripted_writes", "rule_scripted_writes"),
    ("rule_shared_ip", "rule_shared_ip"),
]

_XGBOOST = {"eta": "0.1", "max-depth": "4", "num-boost-round": "200"}
# Depth-1 trees on one feature can only learn a step function of the rule score.
_RULES_ONLY = {"eta": "0.3", "max-depth": "1", "num-boost-round": "20"}


def _variant(model_name, features, hyperparameters):
    return Model(
        version=_MODEL_VERSION,
        inference_spec=InferenceSpec(
            model_backend=ModelBackend.RAY,
            model_backend_params={"model_name": model_name, "model_type": "custom"},
        ),
        input_mapping={
            "instance": "named_struct("
            + ", ".join(f"'{alias}', {source}" for source, alias in features)
            + ")",
        },
        output_mapping={"ato_probability": "score"},
        value_fields=[("score", DataType.DOUBLE)],
        model_artifact_base_uri=_ARTIFACTS,
        output_namespace="public_demo_data",
        training_conf=TrainingSpec(
            training_data_source=EventSource(
                table=ato_training.v1.table,
                query=Query(
                    selects=selects(*[source for source, _ in features], "is_ato", "ds"),
                    start_partition=_TRAIN_START,
                    end_partition=_TRAIN_END,
                ),
            ),
            # The trainer includes both ends: Oct 18 minus 39 days is Sep 9.
            training_data_window=Window(length=39, time_unit=TimeUnit.DAYS),
            schedule="@never",
            python_module="trainer.train",
            resource_config=ResourceConfig(min_replica_count=0, max_replica_count=0),
            job_configs={
                "features": ",".join(f"{source}:{alias}" for source, alias in features),
                "label-column": "is_ato",
                "partition-column": "ds",
                "seed": "42",
                "catalog-type": "glue",
                "catalog-region": "us-west-2",
                # Train on Sep 9 - Oct 11 and validate on the final week, Oct 12 - 18.
                "eval-days": "7",
                **hyperparameters,
            },
        ),
    )


ato_rules_baseline = _variant("ato_rules_baseline", _RULES, _RULES_ONLY)
ato_xgb_velocity = _variant("ato_xgb_velocity", _VELOCITY, _XGBOOST)
ato_xgb_novelty = _variant("ato_xgb_novelty", _NOVELTY, _XGBOOST)
ato_xgb_full = _variant("ato_xgb_full", _FULL, _XGBOOST)
