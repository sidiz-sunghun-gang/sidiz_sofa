"""작업 불가 품목 규칙 관리.

규칙은 JSON 한 파일에 저장하며, 두 가지 형태를 지원한다.
- exact: 품목코드 정확히 일치하면 해당 라인 작업 불가
- pattern: 정규식 패턴이 매칭되면 해당 라인 작업 불가

지원 라인: 1, 3, 4, 5 (당일분배 분배 대상)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import pandas as pd


DEFAULT_LINES = [1, 3, 4, 5]


@dataclass
class LineRules:
    exact: Dict[str, List[str]] = field(default_factory=dict)  # line_no(str) -> [item_code,...]
    pattern: Dict[str, List[str]] = field(default_factory=dict)  # line_no(str) -> [regex,...]

    def forbidden_lines_for(self, item_code: str) -> List[int]:
        """해당 품목코드에 대해 작업 불가인 라인 번호 리스트."""
        if item_code is None:
            return []
        code = str(item_code)
        out = []
        for ln, codes in self.exact.items():
            if code in codes:
                out.append(int(ln))
        for ln, patterns in self.pattern.items():
            for p in patterns:
                if not p:
                    continue
                try:
                    if re.search(p, code):
                        out.append(int(ln))
                        break
                except re.error:
                    continue
        return sorted(set(out))

    def allowed_lines_for(self, item_code: str, lines: List[int] | None = None) -> List[int]:
        lines = lines or DEFAULT_LINES
        forb = set(self.forbidden_lines_for(item_code))
        return [l for l in lines if l not in forb]

    def to_dict(self) -> dict:
        return {"exact": self.exact, "pattern": self.pattern}

    @classmethod
    def from_dict(cls, d: dict) -> "LineRules":
        return cls(
            exact={str(k): list(v) for k, v in (d.get("exact") or {}).items()},
            pattern={str(k): list(v) for k, v in (d.get("pattern") or {}).items()},
        )


def load_rules(path: Path) -> LineRules:
    if not path.exists():
        return LineRules()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return LineRules.from_dict(json.load(f))
    except Exception:
        return LineRules()


def save_rules(path: Path, rules: LineRules) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules.to_dict(), f, ensure_ascii=False, indent=2)


def rules_from_dataframe(df: pd.DataFrame) -> LineRules:
    """업로드된 규칙 파일(엑셀/CSV)을 LineRules로 변환.

    기대 컬럼: line(또는 라인), item_code(또는 품목코드), type(exact|pattern, 기본 exact)
    """
    cols = {c.lower(): c for c in df.columns}
    line_col = cols.get("line") or cols.get("라인") or cols.get("line_no")
    code_col = cols.get("item_code") or cols.get("품목코드") or cols.get("code") or cols.get("pattern")
    type_col = cols.get("type") or cols.get("종류")
    if not line_col or not code_col:
        raise ValueError("규칙 파일에 line/item_code 컬럼이 필요합니다.")

    rules = LineRules()
    for _, row in df.iterrows():
        ln_raw = str(row[line_col]).strip()
        m = re.search(r"(\d+)", ln_raw)
        if not m:
            continue
        ln = m.group(1)
        code = str(row[code_col]).strip()
        if not code or code.lower() == "nan":
            continue
        t = "exact"
        if type_col is not None:
            t = str(row[type_col]).strip().lower() or "exact"
        bucket = rules.exact if t == "exact" else rules.pattern
        bucket.setdefault(ln, []).append(code)
    # dedup
    for d in (rules.exact, rules.pattern):
        for k in list(d.keys()):
            d[k] = sorted(set(d[k]))
    return rules
