"""그룹화 정책.

수주건명 일치 시 같은 라인에 묶는 게 기본이지만,
재고/거점/AS 출고처럼 좌·우 단차 같은 품질 이슈가 없는 케이스는
분할 허용해야 출고일 균등이 가능해진다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# 추천 기본 분할 키워드
DEFAULT_SPLIT_KEYWORDS: list[str] = [
    "재고",
    "센터",
    "AS",
    "매출외",
    "반품",
    "내작",
]


@dataclass
class GroupPolicy:
    split_keywords: List[str] = field(default_factory=lambda: list(DEFAULT_SPLIT_KEYWORDS))

    def should_split(self, order_name: str) -> bool:
        """수주건명에 분할 허용 키워드가 포함되면 True."""
        if not order_name:
            return False
        s = str(order_name)
        for kw in self.split_keywords:
            if not kw:
                continue
            if kw in s:
                return True
        return False

    def to_dict(self) -> dict:
        return {"split_keywords": list(self.split_keywords)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "GroupPolicy":
        if not d:
            return cls()
        kws = d.get("split_keywords")
        if kws is None:
            return cls()
        return cls(split_keywords=[str(x) for x in kws if str(x).strip()])


def load_policy(path: Path) -> GroupPolicy:
    if not path.exists():
        return GroupPolicy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return GroupPolicy.from_dict(json.load(f))
    except Exception:
        return GroupPolicy()


def save_policy(path: Path, policy: GroupPolicy) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(policy.to_dict(), f, ensure_ascii=False, indent=2)
