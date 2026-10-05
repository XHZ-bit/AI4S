"""Field-level condition dimensions for image anomaly detection.

The configuration contains comparison semantics only.  It intentionally has
no paper-specific values, expected result, preferred method, or winner.
"""

IMAGE_ANOMALY_DIMENSIONS = (
    {"name": "dataset", "source": "setting.dataset", "critical": True},
    {
        "name": "dataset_version",
        "source": "setting.dataset_version",
        "critical": True,
    },
    {"name": "defect_scope", "source": "setting.subset", "critical": True},
    {
        "name": "supervision",
        "source": "named:supervision,supervision_mode,label_regime",
        "critical": True,
    },
    {
        "name": "anomaly_sample_usage",
        "source": "named:anomaly_sample_usage,anomaly_samples,synthetic_anomalies",
        "critical": True,
    },
    {
        "name": "pretraining_source",
        "source": "named:pretraining_source,pretrained_on,pretraining",
        "critical": True,
    },
    {"name": "split", "source": "setting.split", "critical": True},
    {
        "name": "input_setting",
        "source": "named:image_resolution,input_resolution,input_size",
        "critical": True,
    },
    {
        "name": "preprocessing",
        "source": "setting.preprocessing",
        "critical": True,
    },
    {
        "name": "evaluation_protocol",
        "source": "setting.evaluation_protocol",
        "critical": True,
    },
    {
        "name": "metric_scope",
        "source": "measurements.metric_scope",
        "critical": True,
    },
    {
        "name": "metric_name",
        "source": "measurements.metric_name",
        "critical": True,
    },
    {
        "name": "metric_scale_and_unit",
        "source": "measurements.metric_scale_and_unit",
        "critical": True,
    },
    {
        "name": "aggregation",
        "source": "measurements.aggregation",
        "critical": True,
    },
)
