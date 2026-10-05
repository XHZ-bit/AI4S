"""Field-level condition dimensions for time-series forecasting."""

TIME_SERIES_DIMENSIONS = (
    {"name": "dataset", "source": "setting.dataset", "critical": True},
    {
        "name": "dataset_version",
        "source": "setting.dataset_version",
        "critical": True,
    },
    {"name": "data_subset", "source": "setting.subset", "critical": True},
    {
        "name": "variable_mode",
        "source": "named:variable_mode,forecast_mode,target_mode",
        "critical": True,
    },
    {
        "name": "target_variables",
        "source": "named:target_variables,target,target_columns",
        "critical": True,
    },
    {
        "name": "context_length",
        "source": "named:context_length,input_length,lookback",
        "critical": True,
    },
    {
        "name": "forecast_horizon",
        "source": "named:forecast_horizon,prediction_length,horizon",
        "critical": True,
    },
    {
        "name": "frequency",
        "source": "named:frequency,sampling_frequency,freq",
        "critical": True,
    },
    {
        "name": "normalization",
        "source": "named:normalization,standardization,scaling",
        "critical": True,
    },
    {"name": "time_split", "source": "setting.split", "critical": True},
    {
        "name": "evaluation_protocol",
        "source": "setting.evaluation_protocol",
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
