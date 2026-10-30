"""T3-owned comparison semantics for the frozen public domain profiles."""

from app.models.research import DomainId

from .image_anomaly import IMAGE_ANOMALY_DIMENSIONS
from .time_series import TIME_SERIES_DIMENSIONS


DOMAIN_DIMENSIONS = {
    DomainId.CUSTOM: tuple({'name':name,'source':'setting.'+name,'critical':True} for name in ['dataset','dataset_version','split','evaluation_protocol']) + tuple({'name':name,'source':'measurements.'+name,'critical':True} for name in ['metric_name','metric_scope','metric_scale_and_unit','aggregation']),
    DomainId.ROBOT_POLICY_LEARNING: tuple({"name":name,"source":"named:"+name,"critical":True} for name in ["task","environment_version","observation_modality","action_space","demonstration_data","evaluation_episodes"]) + ({"name":"split","source":"setting.split","critical":True},{"name":"evaluation_protocol","source":"setting.evaluation_protocol","critical":True},{"name":"metric_name","source":"measurements.metric_name","critical":True},{"name":"metric_scale_and_unit","source":"measurements.metric_scale_and_unit","critical":True},{"name":"aggregation","source":"measurements.aggregation","critical":True}),
    DomainId.IMAGE_ANOMALY_DETECTION: IMAGE_ANOMALY_DIMENSIONS,
    DomainId.TIME_SERIES_FORECASTING: TIME_SERIES_DIMENSIONS,
}

__all__ = ["DOMAIN_DIMENSIONS"]
