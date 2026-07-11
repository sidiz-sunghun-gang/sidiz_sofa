"""품목코드/패턴별 "라인당 최대 1개" 균등분산 규칙.

등록된 품목은 같은 수주건명이어도 그룹으로 묶지 않고 행 단위로 풀어서,
작업 가능한 라인마다 최대 1개씩 고르게 나눠 배정한다. 작업 가능한 라인 수보다
행 수가 많으면(초과분) 부하가 가장 적은 라인부터 순서대로 2번째, 3번째...
행을 추가 배정한다 — 특정 라인 한 곳에 몰아주지 않기 위함.

매칭 우선순위: exact > pattern (가장 구체적인 규칙 우선), rules.py의 방식과 동일.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class LineCap:
    exact: List[str] = field(default_factory=list)      # 품목코드 정확 일치
    pattern: List[str] = field(default_factory=list)     # 정규식 패턴

    def is_capped(self, item_code: str) -> bool:
        if not item_code:
            return False
        code = str(item_code)
        if code in self.exact:
            return True
        for p in self.pattern:
            if not p:
                continue
            try:
                if re.search(p, code):
                    return True
            except re.error:
                continue
        return False

    def to_dict(self) -> dict:
        return {"exact": list(self.exact), "pattern": list(self.pattern)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "LineCap":
        if not d:
            return cls()
        return cls(
            exact=[str(x).strip() for x in (d.get("exact") or []) if str(x).strip()],
            pattern=[str(x).strip() for x in (d.get("pattern") or []) if str(x).strip()],
        )


def load_line_cap(path: Path) -> LineCap:
    if not path.exists():
        return LineCap()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return LineCap.from_dict(json.load(f))
    except Exception:
        return LineCap()


def save_line_cap(path: Path, cap: LineCap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cap.to_dict(), f, ensure_ascii=False, indent=2)


def distribute_rows_capped(
    n_rows: int,
    eligible_lines: List[int],
    load_lookup: Dict[int, float],
) -> List[int]:
    """n_rows개를 eligible_lines에 라인당 최대 1개씩, 부하 적은 라인부터 채워서 배정.

    1라운드: 모든 라인에 1개씩(부하 오름차순) → 2라운드: 다시 부하 오름차순으로 2번째...
    라인 수보다 행이 많으면 자연스럽게 다음 라운드로 넘어가며 이미 배정된 다른
    캡 규칙 물량은 반영하지 않음(품목별로 독립 계산) — load_lookup은 호출 시점의
    "전체 생산" 부하(인당 수량 등)를 넘겨 라운드 간 우선순위만 정하는 데 쓴다.
    """
    if n_rows <= 0 or not eligible_lines:
        return []
    count: Dict[int, int] = {l: 0 for l in eligible_lines}
    out: List[int] = []
    for _ in range(n_rows):
        best = min(eligible_lines, key=lambda l: (count[l], load_lookup.get(l, 0.0), l))
        out.append(best)
        count[best] += 1
    return out
