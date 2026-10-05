from datetime import UTC, datetime

import pytest

from app.models.research import (
    CandidateBundle,
    ComparisonCandidate,
    ComparisonRequest,
    ComputeConstraint,
    EvidenceRef,
    ExperimentSetting,
    FieldEvidence,
    Measurement,
    MethodCard,
    NamedValue,
    NumericValue,
    ProjectConstraints,
    ResearchProject,
)
from app.research.comparison import (
    compare_candidates_to_constraints,
    compare_conditions,
)


NOW = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)


def _evidence(eid: str, paper: str, document: str):
    return EvidenceRef(
        id=eid,
        source_kind="literature_report",
        finding_status="reported",
        kind="text",
        paper_uid=paper,
        document_id=document,
        document_version="sha256:abc",
        passage_id=f"passage-{eid}",
        quote="reported condition",
    )


def _binding(path: str, eid: str, status: str = "reported"):
    return FieldEvidence(
        field_path=path,
        source_kind="literature_report",
        finding_status=status,
        evidence_ids=[eid],
    )


def image_bundle():
    methods = []
    settings = []
    measurements = []
    evidence = []
    for index in (1, 2):
        eid = f"ev-{index}"
        evidence.append(_evidence(eid, f"paper-{index}", f"doc-{index}"))
        method = MethodCard(
            id=f"method-{index}",
            project_id="project-1",
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[_binding("name", eid)],
            paper_link_id=f"link-{index}",
            name=f"Method {index}",
            created_at=NOW,
            updated_at=NOW,
        )
        setting = ExperimentSetting(
            id=f"setting-{index}",
            project_id="project-1",
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[
                _binding("dataset", eid),
                _binding("dataset_version", eid),
                _binding("subset", eid),
                _binding("supervision", eid),
                _binding("anomaly_sample_usage", eid),
                _binding("pretraining_source", eid),
                _binding("split", eid),
                _binding("input_resolution", eid),
                _binding("evaluation_protocol", eid),
            ],
            paper_link_id=f"link-{index}",
            method_id=method.id,
            name=f"Setting {index}",
            dataset="MVTec AD",
            dataset_version="1.0",
            subset="all categories",
            split="official",
            evaluation_protocol="official test split",
            preprocessing=["resize 256", "center crop 224"],
            hyperparameters=[
                NamedValue(name="supervision", value="one-class"),
                NamedValue(name="anomaly_sample_usage", value="none"),
                NamedValue(name="pretraining_source", value="ImageNet-1K"),
                NamedValue(name="input_resolution", value="224x224"),
            ],
            resources=[NamedValue(name="training_time", value=2, unit="hour")],
            created_at=NOW,
            updated_at=NOW,
        )
        measurement = Measurement(
            id=f"measurement-{index}",
            project_id="project-1",
            version=1,
            source_kind="literature_report",
            finding_status="reported",
            field_evidence=[
                _binding("metric_name", eid),
                _binding("metric_scope", eid),
                _binding("aggregation", eid),
                _binding("value", eid),
            ],
            experiment_setting_id=setting.id,
            metric_name="image_auroc",
            metric_scope="image",
            value=NumericValue(value=0.9, scale="fraction"),
            aggregation="macro across categories",
            created_at=NOW,
            updated_at=NOW,
        )
        methods.append(method)
        settings.append(setting)
        measurements.append(measurement)
    return CandidateBundle(
        project_id="project-1",
        paper_link_id="bundle-link",
        document_id="bundle-doc",
        document_version="sha256:bundle",
        extraction_version="test-v1",
        evidence=evidence,
        methods=methods,
        experiment_settings=settings,
        measurements=measurements,
    )


def request(domain="image_anomaly_detection"):
    return ComparisonRequest(
        project_id="project-1",
        project_version=3,
        domain=domain,
        candidates=[
            ComparisonCandidate(
                method_id="method-1",
                experiment_setting_id="setting-1",
                measurement_ids=["measurement-1"],
            ),
            ComparisonCandidate(
                method_id="method-2",
                experiment_setting_id="setting-2",
                measurement_ids=["measurement-2"],
            ),
        ],
    )


def dimension(result, name):
    return next(item for item in result.dimensions if item.name == name)


CONSISTENT_DIMENSIONS = [
    "dataset",
    "dataset_version",
    "defect_scope",
    "supervision",
    "anomaly_sample_usage",
    "pretraining_source",
    "split",
    "input_setting",
]


@pytest.mark.parametrize("name", CONSISTENT_DIMENSIONS)
def test_eight_dimensions_report_verified_consistency(name):
    result = compare_conditions(request(), image_bundle())
    item = dimension(result, name)
    assert item.comparable is True
    assert "判断=已核对维度一致" in item.reason
    assert "证据=ev-1, ev-2" in item.reason
    assert "不代表科学上完全可比" in item.reason


def _change_second(bundle, dimension_name, *, missing=False):
    setting = bundle.experiment_settings[1]
    if dimension_name == "dataset":
        setting.dataset = None if missing else "VisA"
    elif dimension_name == "dataset_version":
        setting.dataset_version = None if missing else "2.0"
    elif dimension_name == "defect_scope":
        setting.subset = None if missing else "bottle only"
    elif dimension_name == "split":
        setting.split = None if missing else "custom random split"
    else:
        aliases = {
            "supervision": "supervision",
            "anomaly_sample_usage": "anomaly_sample_usage",
            "pretraining_source": "pretraining_source",
            "input_setting": "input_resolution",
        }
        key = aliases[dimension_name]
        setting.hyperparameters = [
            item
            for item in setting.hyperparameters
            if item.name != key
        ]
        if not missing:
            setting.hyperparameters.append(NamedValue(name=key, value="different"))


@pytest.mark.parametrize("name", CONSISTENT_DIMENSIONS)
def test_eight_dimensions_report_differences(name):
    bundle = image_bundle()
    _change_second(bundle, name, missing=False)
    item = dimension(compare_conditions(request(), bundle), name)
    assert item.comparable is False
    assert "判断=存在差异" in item.reason
    assert "差异=setting-1=" in item.reason
    assert "setting-2=" in item.reason


@pytest.mark.parametrize("name", CONSISTENT_DIMENSIONS)
def test_eight_dimensions_report_missing_information(name):
    bundle = image_bundle()
    _change_second(bundle, name, missing=True)
    item = dimension(compare_conditions(request(), bundle), name)
    assert item.comparable is False
    assert "判断=信息不足" in item.reason
    assert "缺失=setting-2:" in item.reason


def test_difference_and_missing_are_both_retained():
    bundle = image_bundle()
    bundle.methods.append(
        bundle.methods[1].model_copy(update={"id": "method-3", "name": "Method 3"})
    )
    bundle.experiment_settings.append(
        bundle.experiment_settings[1].model_copy(
            update={"id": "setting-3", "method_id": "method-3", "dataset": None}
        )
    )
    bundle.measurements.append(
        bundle.measurements[1].model_copy(
            update={"id": "measurement-3", "experiment_setting_id": "setting-3"}
        )
    )
    bundle.experiment_settings[1].dataset = "VisA"
    req = request().model_copy(
        update={
            "candidates": [
                *request().candidates,
                ComparisonCandidate(
                    method_id="method-3",
                    experiment_setting_id="setting-3",
                    measurement_ids=["measurement-3"],
                ),
            ]
        }
    )
    item = dimension(compare_conditions(req, bundle), "dataset")
    assert "判断=存在差异+信息不足" in item.reason
    assert "VisA" in item.reason
    assert "setting-3:dataset" in item.reason


def test_metric_scope_scale_and_aggregation_never_collapse():
    bundle = image_bundle()
    second = bundle.measurements[1]
    second.metric_scope = "pixel"
    second.value = NumericValue(value=90, unit="%", scale="percent")
    second.aggregation = "micro over pixels"
    result = compare_conditions(request(), bundle)
    assert "存在差异" in dimension(result, "metric_scope").reason
    # Fraction and percent conversion is mathematically defined, but the raw
    # values remain present. A differing unit still prevents accidental merge.
    assert dimension(result, "metric_scale_and_unit").values["setting-2"] == "percent (%)"
    assert "存在差异" in dimension(result, "metric_scale_and_unit").reason
    assert "存在差异" in dimension(result, "aggregation").reason
    assert any("禁止跨组" in warning for warning in result.warnings)


def test_conflicting_evidence_is_visible_even_when_values_match():
    bundle = image_bundle()
    setting = bundle.experiment_settings[1]
    setting.field_evidence = [
        binding.model_copy(update={"finding_status": "conflicting"})
        if binding.field_path == "dataset"
        else binding
        for binding in setting.field_evidence
    ]
    item = dimension(compare_conditions(request(), bundle), "dataset")
    assert item.comparable is False
    assert "判断=存在差异" in item.reason
    assert "冲突证据=ev-2" in item.reason


def project(*, excluded=None, notes=None, time_budget=None, compute=None):
    return ResearchProject(
        id="project-1",
        version=3,
        title="课题",
        research_question="问题",
        domain="image_anomaly_detection",
        domain_profile_version="image-anomaly-v1",
        constraints=ProjectConstraints(
            version=2,
            objective="验证首轮路线",
            excluded_datasets=excluded or [],
            required_metrics=["image_auroc"],
            compute=compute or [],
            time_budget=time_budget,
            notes=notes or [],
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def test_hard_constraint_conflict_and_preference_are_distinct():
    result = compare_candidates_to_constraints(
        project(excluded=["MVTec AD"], notes=["偏好更小的模型"]), image_bundle()
    )
    hard = dimension(result, "dataset_policy")
    preference = dimension(result, "preferences")
    assert "判断=已知冲突" in hard.reason
    assert "excluded_datasets" in hard.reason
    assert "判断=尚未发现冲突" in preference.reason
    assert "偏好仅用于提示，不作为硬约束淘汰候选" in preference.reason


def test_provable_time_conversion_records_original_and_proof():
    bundle = image_bundle()
    bundle.experiment_settings[0].resources = [
        NamedValue(name="training_time", value=120, unit="minute")
    ]
    result = compare_candidates_to_constraints(
        project(time_budget=NumericValue(value=3, unit="hour")), bundle
    )
    item = dimension(result, "time_budget")
    assert item.values["setting-1"] == "120 minute"
    assert "按固定因子换算" in item.reason
    assert "判断=尚未发现冲突" in item.reason


def test_unprovable_unit_conversion_stays_information_insufficient():
    bundle = image_bundle()
    bundle.experiment_settings[0].resources = [
        NamedValue(name="training_time", value=2, unit="GPU-day-estimate")
    ]
    result = compare_candidates_to_constraints(
        project(time_budget=NumericValue(value=3, unit="hour")), bundle
    )
    item = dimension(result, "time_budget")
    assert "判断=信息不足" in item.reason
    assert "无法证明" in item.reason


def test_missing_resource_information_is_not_guessed():
    bundle = image_bundle()
    bundle.experiment_settings[0].resources = []
    result = compare_candidates_to_constraints(
        project(compute=[ComputeConstraint(device_kind="gpu")]), bundle
    )
    item = dimension(result, "compute")
    assert "判断=信息不足" in item.reason
    assert "setting-1:compute" in item.reason


def test_reported_compute_requirement_can_be_a_known_hard_conflict():
    bundle = image_bundle()
    bundle.experiment_settings[0].resources = [
        NamedValue(name="device_kind", value="tpu"),
        NamedValue(name="device_count", value=8),
    ]
    result = compare_candidates_to_constraints(
        project(compute=[ComputeConstraint(device_kind="gpu", device_count=1)]), bundle
    )
    item = dimension(result, "compute")
    assert "判断=已知冲突" in item.reason
    assert "需求设备 tpu" in item.reason
    assert "需求设备数 8" in item.reason


def test_explicit_domain_avoids_guessing_from_ambiguous_metric_names():
    bundle = image_bundle()
    for measurement in bundle.measurements:
        measurement.metric_name = "score"
        measurement.metric_scope = None
    for setting in bundle.experiment_settings:
        setting.hyperparameters = []
    result = compare_conditions(request("image_anomaly_detection"), bundle)
    assert dimension(result, "dataset").comparable is True


def test_time_series_profile_covers_subset_lengths_scaling_and_aggregation():
    bundle = image_bundle()
    for setting in bundle.experiment_settings:
        setting.dataset = "ETTh1"
        setting.subset = "train through month 12"
        setting.split = "chronological 12/4/4 months"
        setting.hyperparameters = [
            NamedValue(name="variable_mode", value="multivariate"),
            NamedValue(name="target_variables", value="OT"),
            NamedValue(name="context_length", value=96, unit="step"),
            NamedValue(name="forecast_horizon", value=24, unit="step"),
            NamedValue(name="frequency", value="hourly"),
            NamedValue(name="normalization", value="train-set z-score"),
        ]
    for measurement in bundle.measurements:
        measurement.metric_name = "rmse"
        measurement.metric_scope = "OT"
        measurement.aggregation = "mean over forecast windows"
        measurement.value = NumericValue(value=0.4, unit="scaled target", scale="raw")
    result = compare_conditions(request("time_series_forecasting"), bundle)
    names = {item.name for item in result.dimensions}
    assert {
        "data_subset",
        "variable_mode",
        "context_length",
        "forecast_horizon",
        "normalization",
        "time_split",
        "aggregation",
    }.issubset(names)
    assert dimension(result, "forecast_horizon").comparable is True
    bundle.experiment_settings[1].hyperparameters = [
        item.model_copy(update={"value": 48})
        if item.name == "forecast_horizon"
        else item
        for item in bundle.experiment_settings[1].hyperparameters
    ]
    changed = compare_conditions(request("time_series_forecasting"), bundle)
    assert "存在差异" in dimension(changed, "forecast_horizon").reason
