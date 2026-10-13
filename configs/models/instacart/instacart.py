"""Fixed-data next-basket tutorial: popularity baseline versus shopper history.

Both variants use the demo's shared Ray/XGBoost trainer archive. Verify
that archive under each model name in the demo artifact bucket before training;
see docs/data_sources.md. No Databricks credentials or catalog are required.
"""

from joins.instacart import instacart_join
from teams import ARTIFACT_PREFIX

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

# Product popularity and overall shopper behavior, without shopper-product history.
_BASELINE = [
    ("product_id_user_id_count_365d", "product_purchases"),
    ("product_id_user_id_approx_unique_count_365d", "product_buyers"),
    ("product_id_reordered_average_365d", "product_reorder_rate"),
    ("product_id_add_to_cart_order_average_365d", "product_cart_position"),
    ("user_id_order_id_approx_unique_count_365d", "user_orders"),
    ("user_id_item_approx_unique_count_365d", "user_distinct_items"),
    ("user_id_reordered_average_365d", "user_reorder_rate"),
]

_WITH_HISTORY = _BASELINE + [
    ("user_id_product_id_order_id_count_7d", "pair_count_7d"),
    ("user_id_product_id_order_id_count_14d", "pair_count_14d"),
    ("user_id_product_id_order_id_count_45d", "pair_count_45d"),
    ("user_id_product_id_add_to_cart_order_average_365d", "pair_cart_position"),
    ("user_id_product_id_reordered_average_365d", "pair_reorder_rate"),
    ("share_of_orders_with_product", "share_of_orders"),
    ("recent_share_of_product_purchases", "recent_share"),
    ("days_since_last_purchase", "days_since_last"),
    ("product_share_of_basket", "share_of_basket"),
]


def _variant(model_name, features):
    return Model(
        version="19ca8c1c152c",
        inference_spec=InferenceSpec(
            model_backend=ModelBackend.RAY,
            model_backend_params={"model_name": model_name, "model_type": "custom"},
        ),
        input_mapping={
            "instance": "named_struct("
            + ", ".join(f"'{alias}', {source}" for source, alias in features)
            + ")",
        },
        output_mapping={"will_reorder": "score"},
        value_fields=[("score", DataType.DOUBLE)],
        model_artifact_base_uri=ARTIFACT_PREFIX,
        output_namespace="public_demo_data",
        training_conf=TrainingSpec(
            training_data_source=EventSource(
                table=instacart_join.v1.table,
                query=Query(
                    selects=selects(
                        *[source for source, _ in features], "in_next_basket", "ds"
                    ),
                    start_partition="2026-08-18",
                    end_partition="2026-08-24",
                ),
            ),
            # The trainer includes both ends: Aug 24 minus 6 days is Aug 18.
            training_data_window=Window(length=6, time_unit=TimeUnit.DAYS),
            schedule="@never",
            python_module="trainer.train",
            resource_config=ResourceConfig(min_replica_count=0, max_replica_count=0),
            job_configs={
                "features": ",".join(f"{source}:{alias}" for source, alias in features),
                "label-column": "in_next_basket",
                "partition-column": "ds",
                "seed": "42",
                "catalog-type": "glue",
                "catalog-region": "us-west-2",
                "eta": "0.1",
                "max-depth": "6",
                "num-boost-round": "100",
                # The final partition holds out whole shoppers via the staging hash.
                "eval-days": "1",
                "thresholds": "validation_auc>=0.70",
            },
        ),
    )


# Distinct backend names keep archives and training reports separate.
instacart_basket_baseline = _variant("instacart_basket_baseline", _BASELINE)
instacart_basket_model = _variant("instacart_basket_model", _WITH_HISTORY)
