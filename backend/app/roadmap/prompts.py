import json


def build_target_parse_messages(goal: str) -> list[dict]:
    return [
        {"role": "system", "content": "你是科研图谱助手。把用户目标解析为单个核心概念/方法名。返回JSON {\"concept\": \"名称\"}。"},
        {"role": "user", "content": goal},
    ]


def build_packaging_messages(skeleton: dict, profile) -> list[dict]:
    return [
        {"role": "system", "content": (
            "你是科研路线规划师。根据骨架JSON与学习者画像，生成阶段化路线。"
            "返回JSON {\"phases\":[{\"phase\":int,\"title\":str,\"weeks\":str,"
            "\"items\":[{\"kind\":\"paper|experiment|resource\",\"uid\":str|null,"
            "\"title\":str,\"reason\":str,\"evidence\":str,\"difficulty\":float|null,"
            "\"done\":false}]}],\"innovations\":[{\"title\":str,\"rationale\":str,\"evidence\":str}]}。"
            "阶段数与骨架一致，保留骨架中论文与实验uid。"
        )},
        {"role": "user", "content": json.dumps(
            {"skeleton": skeleton, "profile": profile.model_dump()}, ensure_ascii=False
        )},
    ]
