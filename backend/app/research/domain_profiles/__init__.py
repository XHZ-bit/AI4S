"""T3-owned comparison semantics for the frozen public domain profiles."""

from app.models.research import DomainId

from .image_anomaly import IMAGE_ANOMALY_DIMENSIONS
from .time_series import TIME_SERIES_DIMENSIONS


DOMAIN_DIMENSIONS = {
    DomainId.IMAGE_ANOMALY_DETECTION: IMAGE_ANOMALY_DIMENSIONS,
    DomainId.TIME_SERIES_FORECASTING: TIME_SERIES_DIMENSIONS,
}

__all__ = ["DOMAIN_DIMENSIONS"]
