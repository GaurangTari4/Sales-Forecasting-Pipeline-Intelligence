"""Point-in-time feature and target construction for forecast snapshots."""

from .builder import build_feature_dataset, build_labels
from .contracts import FeatureConfig, FEATURE_SCHEMA_VERSION
from .persistence import persist_feature_dataset
from .leakage import FeatureLeakageError, assert_temporal_integrity

__all__ = ["FEATURE_SCHEMA_VERSION", "FeatureConfig", "build_feature_dataset", "build_labels", "persist_feature_dataset", "FeatureLeakageError", "assert_temporal_integrity"]
