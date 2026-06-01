"""품목코드별 라인 분할 락 — 정확 일치(exact) + 정규식 패턴(pattern) 지원.

데이터 모델:
- exact:   {품목코드 → {라인번호: 가중치}}   ← 코드 100% 일치 시 적용
- pattern: {정규식 → {라인번호: 가중치}}     ← 정규식 매칭되는 모든 품목에 적용

매칭 우선순위: exact > pattern (가장 구체적인 규칙 우선)

예:
- exact["ACSB3201BN"] = {1:1, 3:3, 4:1, 5:1}
- pattern["^ACSB3201"] = {1:1, 3:3, 4:1, 5:1}   → 같은 모델의 모든 색상 한꺼번에
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


@dataclass
class SplitLock:
    exact: Dict[str, Dict[int, float]] = field(default_factory=dict)
    pattern: Dict[str, Dict[int, float]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 매칭
    # ------------------------------------------------------------------
    def find_match(self, item_code: str) -> Tuple[str, str, Dict[int, float]] | None:
        """품목코드에 매칭되는 락을 찾는다.

        Returns: (type, key, weights) 또는 None
        - type: 'exact' 또는 'pattern'
        - key:  exact 코드 또는 pattern 정규식 문자열
        """
        if not item_code:
            return None
        code = str(item_code)
        if code in self.exact:
            return ("exact", code, self.exact[code])
        for pat, weights in self.pattern.items():
            if not pat:
                continue
            try:
                if re.search(pat, code):
                    return ("pattern", pat, weights)
            except re.error:
                continue
        return None

    def is_locked(self, item_code: str) -> bool:
        return self.find_match(item_code) is not None

    def all_entries(self) -> List[Tuple[str, str, Dict[int, float]]]:
        """전체 락을 (type, key, weights) 리스트로. UI 렌더용."""
        out: List[Tuple[str, str, Dict[int, float]]] = []
        for code, w in self.exact.items():
            out.append(("exact", code, w))
        for pat, w in self.pattern.items():
            out.append(("pattern", pat, w))
        return out

    # ------------------------------------------------------------------
    # 직렬화
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        def _serialize(d: Dict[str, Dict[int, float]]) -> dict:
            return {k: {str(l): float(w) for l, w in v.items()} for k, v in d.items()}
        return {"exact": _serialize(self.exact), "pattern": _serialize(self.pattern)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "SplitLock":
        """JSON에서 락을 복원. 0 비중도 유지 (UI에서 미설정 상태로 카드 표시 가능).

        과거 형식(locks: {...})도 자동 변환 — 모두 exact로 취급.
        """
        if not d:
            return cls()
        # 신규 형식
        if ("exact" in d) or ("pattern" in d):
            return cls(
                exact=cls._load_section(d.get("exact")),
                pattern=cls._load_section(d.get("pattern")),
            )
        # 과거 형식 (locks 단일 dict) 호환
        if "locks" in d:
            return cls(exact=cls._load_section(d.get("locks")))
        return cls()

    @staticmethod
    def _load_section(section: dict | None) -> Dict[str, Dict[int, float]]:
        out: Dict[str, Dict[int, float]] = {}
        if not section:
            return out
        for key, weights in section.items():
            cleaned: Dict[int, float] = {}
            for line_key, w in (weights or {}).items():
                try:
                    line = int(re.search(r"\d+", str(line_key)).group())
                    wv = float(w)
                except (TypeError, ValueError, AttributeError):
                    continue
                if wv >= 0:
                    cleaned[line] = wv
            if cleaned:
                out[str(key).strip()] = cleaned
        return out


def load_split_lock(path: Path) -> SplitLock:
    if not path.exists():
        return SplitLock()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return SplitLock.from_dict(json.load(f))
    except Exception:
        return SplitLock()


def save_split_lock(path: Path, lock: SplitLock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lock.to_dict(), f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
# 가중치 → 행 분배
# ----------------------------------------------------------------------
def distribute_rows_by_weight(
    n_rows: int,
    weights: Dict[int, float],
) -> List[int]:
    """N개 행을 가중치 비율대로 라인에 분배. 각 행의 라인번호 리스트 반환.

    예: n_rows=6, weights={1:1, 3:3, 4:1, 5:1} → [1, 3, 3, 3, 4, 5]
    """
    if n_rows <= 0 or not weights:
        return []
    total_w = sum(weights.values())
    if total_w <= 0:
        return [next(iter(weights))] * n_rows

    allocations: Dict[int, int] = {l: int(n_rows * w / total_w) for l, w in weights.items()}
    remaining = n_rows - sum(allocations.values())
    lines_sorted = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    idx = 0
    while remaining > 0:
        allocations[lines_sorted[idx % len(lines_sorted)][0]] += 1
        remaining -= 1
        idx += 1

    out: List[int] = []
    for line in sorted(allocations.keys()):
        out.extend([line] * allocations[line])
    return out


# ----------------------------------------------------------------------
# 파일 업로드 → SplitLock
# ----------------------------------------------------------------------
def split_lock_from_dataframe(df: pd.DataFrame) -> SplitLock:
    """업로드된 분할 락 파일(엑셀/CSV)을 SplitLock으로 변환.

    Long 형식 (권장):
        item_code, line, weight, type(exact|pattern, 선택; 기본 exact)
        - item_code가 정규식이면 type=pattern 으로 지정

    Wide 형식:
        item_code, line_1, line_3, line_4, line_5, type(선택)
    """
    if df is None or df.empty:
        return SplitLock()

    cols = {c.lower(): c for c in df.columns}
    code_col = cols.get("item_code") or cols.get("품목코드") or cols.get("code") or cols.get("pattern")
    if not code_col:
        raise ValueError("파일에 'item_code' 또는 '품목코드' 컬럼이 필요합니다.")
    type_col = cols.get("type") or cols.get("종류")

    exact: Dict[str, Dict[int, float]] = {}
    pattern: Dict[str, Dict[int, float]] = {}

    line_col = cols.get("line") or cols.get("라인")
    weight_col = cols.get("weight") or cols.get("가중치") or cols.get("비율")

    def _bucket(t: str) -> Dict[str, Dict[int, float]]:
        return pattern if str(t or "").strip().lower() == "pattern" else exact

    if line_col and weight_col:
        # Long 형식
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            if not code or code.lower() == "nan":
                continue
            m = re.search(r"\d+", str(row[line_col]))
            if not m:
                continue
            line = int(m.group())
            try:
                w = float(row[weight_col])
            except (TypeError, ValueError):
                continue
            if w <= 0:
                continue
            t = row[type_col] if type_col is not None else "exact"
            _bucket(t).setdefault(code, {})[line] = w
    else:
        # Wide 형식
        line_cols: Dict[int, str] = {}
        for lower, orig in cols.items():
            m = re.search(r"line[_\s]*(\d+)|(\d+)\s*라인", lower)
            if m:
                line = int(m.group(1) or m.group(2))
                line_cols[line] = orig
        if not line_cols:
            raise ValueError(
                "Wide 형식이면 line_1, line_3 같은 컬럼이 필요합니다. "
                "또는 Long 형식 (item_code, line, weight) 으로 작성하세요."
            )
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            if not code or code.lower() == "nan":
                continue
            entry: Dict[int, float] = {}
            for line, col in line_cols.items():
                try:
                    w = float(row[col])
                except (TypeError, ValueError):
                    continue
                if w > 0:
                    entry[line] = w
            if entry:
                t = row[type_col] if type_col is not None else "exact"
                _bucket(t)[code] = entry

    return SplitLock(exact=exact, pattern=pattern)
