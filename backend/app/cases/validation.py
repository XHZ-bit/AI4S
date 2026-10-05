"""Bounded import contracts; recompute consistency, never certify remote execution."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.cases.catalog import CASE_ID, VERSION, SOURCES, CHECK_IDS, LIMITATION


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Environment(StrictModel):
    python: str = Field(min_length=1, max_length=80)
    system: str = Field(min_length=1, max_length=80)
    machine: str = Field(min_length=1, max_length=80)


class FileResult(StrictModel):
    path: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CheckResult(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    passed: bool


class Bundle(StrictModel):
    schema_version: Literal[1]
    case_id: str = Field(max_length=100)
    case_version: str = Field(max_length=30)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    scope: Literal["source_inspection"]
    run_id: str = Field(max_length=36)
    created_at: str = Field(max_length=50)
    environment: Environment
    files: list[FileResult] = Field(max_length=8)
    checks: list[CheckResult] = Field(max_length=16)
    errors: list[str] = Field(max_length=16)


def validate_bundle(bundle):
    if bundle.case_id != CASE_ID or bundle.case_version != VERSION:
        raise ValueError("结果包不属于当前专题版本，请使用本页工具")
    try:
        UUID(bundle.run_id)
        timestamp = datetime.fromisoformat(bundle.created_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError()
    except ValueError as exc:
        raise ValueError("运行标识或时间格式不正确") from exc
    if any(len(e) > 1000 for e in bundle.errors):
        raise ValueError("错误摘要过长")
    if len({f.path for f in bundle.files}) != len(bundle.files) or len(
        {c.id for c in bundle.checks}
    ) != len(bundle.checks):
        raise ValueError("存在重复文件或检查项")
    expected = {f["path"]: f["sha256"] for f in SOURCES["files"]}
    if any(f.path not in expected for f in bundle.files) or any(
        c.id not in CHECK_IDS for c in bundle.checks
    ):
        raise ValueError("结果包包含未知文件或检查项")
    rows = [
        {
            "id": "commit",
            "label": "固定代码版本",
            "passed": bundle.commit == SOURCES["commit"],
        }
    ]
    observed = {f.path: f.sha256 for f in bundle.files}
    rows.extend(
        {"id": path, "label": path, "passed": observed.get(path) == digest}
        for path, digest in expected.items()
    )
    labels = [
        "Python 3.10+",
        "动作预测接口",
        "观测输入形状",
        "动作输出形状",
        "20 维观测配置",
        "2 维动作配置",
        "检查点参数",
        "评估日志位置",
    ]
    checks = {c.id: c.passed for c in bundle.checks}
    version = re.match(r"^(\d+)\.(\d+)(?:\.|$)", bundle.environment.python)
    python_ok = bool(version and tuple(map(int, version.groups())) >= (3, 10))
    rows.extend(
        {
            "id": key,
            "label": label,
            "passed": bool(checks.get(key, False))
            and (python_ok if key == "python_version" else True),
        }
        for key, label in zip(CHECK_IDS, labels)
    )
    rows.append(
        {"id": "no_errors", "label": "工具未报告错误", "passed": not bundle.errors}
    )
    passed = all(r["passed"] for r in rows)
    return {
        "status": "metadata_consistent" if passed else "needs_attention",
        "passed": passed,
        "checks": rows,
        "notice": LIMITATION,
        "verification": "用户导入记录；服务端核对了预期版本、散列与字段，不是独立执行认证。",
        "scope": "source_inspection",
    }
