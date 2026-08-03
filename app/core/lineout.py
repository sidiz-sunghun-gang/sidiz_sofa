"""라인 OUT(연차·반차) 처리 — 이미 분배/집계된 결과에서 특정 라인의 품목만 재분배.

요구사항:
- OUT 처리된 라인에 배정된 품목만 나머지 라인으로 재배정한다.
- 다른 라인에 이미 배정된 품목은 절대 변경하지 않는다 (현장 라인 혼선 방지).
- 같은 수주건명 그룹은 재배정 시에도 한 라인에 묶어서 이동한다 (좌/우 단차 등 품질 이슈).
- OUT 라인 전용 품목(다른 라인에서는 작업 불가)은 재배정하지 않고 "재배정 불가"로 표시한다.

당일분배(자동 배정 결과)와 누적분배(ERP 원본 라인 값을 그대로 쓰는 미착수 잔여 물량)
양쪽 모두에 같은 재배정 규칙을 적용할 수 있도록 핵심 로직(`_redistribute_rows`)을
라인 라벨 컬럼명만 다르게 받아 공유한다.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .cumulative import build_cumulative_result
from .daily import build_daily_result, FINISHED_KEYWORDS
from .lines import LINE_HEADCOUNT as _LINE_HC, LINE_FINISHED, line_label
from .rules import LineRules


def _row_allowed(rules: LineRules, code, name, candidate_lines: List[int]) -> List[int]:
    """daily.py의 `_row_allowed`와 동일한 규칙: 품목명에 반제품 키워드가 있으면
    반제품 라인(LINE_FINISHED) 전용 — 그 라인이 후보에서 빠졌다면(OUT 등) 재배정 불가(빈 리스트).
    """
    nm = str(name or "")
    for kw in FINISHED_KEYWORDS:
        if kw in nm:
            return [LINE_FINISHED] if LINE_FINISHED in candidate_lines else []
    return rules.allowed_lines_for(str(code), lines=candidate_lines)


def _redistribute_rows(
    df: pd.DataFrame,
    line_col: str,
    rules: LineRules,
    out_lines: List[int],
    target_lines: List[int],
    headcount: Dict[int, int],
    note_col: str | None = None,
) -> Tuple[pd.DataFrame, int, pd.DataFrame]:
    """`line_col`에 담긴 라인 라벨을 기준으로 OUT 라인 행만 재배정.

    Returns: (수정된 df, 이동 건수, 재배정 불가 상세 df)
    """
    remain_lines = [l for l in target_lines if l not in out_lines]
    out_labels = {line_label(l) for l in out_lines}

    out = df.copy()
    if line_col not in out.columns or not out_lines or not remain_lines:
        return out, 0, out.iloc[0:0]

    out_mask = out[line_col].isin(out_labels)
    if not out_mask.any():
        return out, 0, out.iloc[0:0]

    # 재배정 전 나머지 라인 부하 (OUT 라인 품목은 아직 포함 안 됨 → 그대로 초기치로 사용)
    load_qty: Dict[int, float] = {}
    load_sec: Dict[int, float] = {}
    for l in remain_lines:
        sub = out[out[line_col] == line_label(l)]
        load_qty[l] = float(sub["plan_qty"].sum()) if "plan_qty" in sub.columns else 0.0
        load_sec[l] = float(sub["plan_sec"].sum()) if "plan_sec" in sub.columns else 0.0

    out_rows = out[out_mask]
    names_col = (
        out_rows["item_name"].fillna("") if "item_name" in out_rows.columns
        else pd.Series([""] * len(out_rows), index=out_rows.index)
    )
    raw_keys = (
        out_rows["order_name"].fillna("").astype(str).str.strip()
        if "order_name" in out_rows.columns
        else pd.Series([""] * len(out_rows), index=out_rows.index)
    )
    solo_marks = pd.Series([f"__solo_{i}__" for i in range(len(out_rows))], index=out_rows.index)
    group_key = raw_keys.where(raw_keys != "", solo_marks)

    groups = []
    for _gkey, gdf in out_rows.groupby(group_key, sort=False):
        allowed_sets = [
            set(_row_allowed(
                rules,
                gdf.loc[idx, "item_code"] if "item_code" in gdf.columns else None,
                names_col.loc[idx],
                remain_lines,
            ))
            for idx in gdf.index
        ]
        allowed = sorted(set.intersection(*allowed_sets)) if allowed_sets else []
        groups.append({
            "indices": gdf.index.tolist(),
            "allowed": allowed,
            "total_qty": float(gdf["plan_qty"].sum()) if "plan_qty" in gdf.columns else 0.0,
            "total_sec": float(gdf["plan_sec"].sum()) if "plan_sec" in gdf.columns else 0.0,
        })

    # 물량 큰 그룹부터 먼저 처리 — 부하가 낮은 좋은 라인 자리를 먼저 확보
    groups.sort(key=lambda g: (-g["total_qty"], -g["total_sec"]))

    moved_idx: List[int] = []
    unmovable_idx: List[int] = []
    for g in groups:
        allowed = g["allowed"]
        if not allowed:
            unmovable_idx.extend(g["indices"])
            continue
        best = min(
            allowed,
            key=lambda l: (
                load_qty.get(l, 0.0) / max(1, headcount.get(l, 1)),
                load_sec.get(l, 0.0) / max(1, headcount.get(l, 1)),
                l,
            ),
        )
        out.loc[g["indices"], line_col] = line_label(best)
        if note_col:
            out.loc[g["indices"], note_col] = (
                "재배정(" + ",".join(line_label(l) for l in allowed) + ")"
            )
        load_qty[best] = load_qty.get(best, 0.0) + g["total_qty"]
        load_sec[best] = load_sec.get(best, 0.0) + g["total_sec"]
        moved_idx.extend(g["indices"])

    if unmovable_idx and note_col:
        out.loc[unmovable_idx, note_col] = "(재배정 불가 - OUT라인 전용 품목)"

    unmovable = out.loc[unmovable_idx].copy() if unmovable_idx else out.iloc[0:0]
    return out, len(moved_idx), unmovable


def redistribute_out_lines(
    assigned_df: pd.DataFrame,
    rules: LineRules,
    out_lines: List[int],
    target_lines: List[int],
    headcount: Dict[int, int] | None = None,
) -> dict:
    """[당일분배] OUT 라인에 배정된 품목만 나머지 라인으로 재배정한 결과를 반환.

    Returns:
        detail/summary/combined/assigned_df: `daily.build_daily_result`와 동일한 형태
            (OUT 라인 품목만 배정라인이 바뀌고, 그 외 라인의 행은 원본 그대로 유지됨)
        moved: 재배정된 행 수
        unmovable: 재배정 불가(다른 라인이 작업 불가한 전용 품목) 상세 DataFrame
    """
    headcount = headcount or _LINE_HC
    full, moved, unmovable = _redistribute_rows(
        assigned_df, "배정라인", rules, out_lines, target_lines, headcount, note_col="후보라인",
    )
    result = build_daily_result(full, target_lines, headcount)
    result["moved"] = moved
    result["unmovable"] = unmovable
    return result


def redistribute_out_lines_cumulative(
    raw_filtered: pd.DataFrame,
    rules: LineRules,
    out_lines: List[int],
    target_lines: List[int],
    headcount: Dict[int, int] | None = None,
) -> dict:
    """[누적분배] 아직 미착수된 누적 잔여 물량 중 OUT 라인 몫만 나머지 라인으로 재배정.

    `raw_filtered`는 `cumulative.process_cumulative()`가 반환하는 필터링된 원본
    (라인 라벨이 "line" 컬럼에 있음). 나머지 동작은 당일분배 재배정과 동일하다.
    """
    headcount = headcount or _LINE_HC
    work, moved, unmovable = _redistribute_rows(
        raw_filtered, "line", rules, out_lines, target_lines, headcount,
    )
    result = build_cumulative_result(work)
    result["moved"] = moved
    result["unmovable"] = unmovable
    return result
