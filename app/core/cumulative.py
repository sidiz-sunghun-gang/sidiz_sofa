"""누적분배 처리.

- 재공완료(Y) 제거
- 생산라인 1·3·4·5라인(분배 대상) + 8·9라인(참고)을 표시
- 라인(담당자 포함) × 출고일자 — 한 표에 수량/시간을 함께 표시
"""
from __future__ import annotations

import pandas as pd

# 분배 대상 라인 (참고: 누적분배 자체는 단순 표시지만, UI 색상 강조에 사용)
CUMUL_TARGET_LINES = [1, 3, 4, 5]
# 표시 라인 (8·9라인을 참고용으로 함께 노출)
CUMUL_DISPLAY_LINES = [1, 3, 4, 5, 8, 9]


def process_cumulative(
    df: pd.DataFrame,
    *,
    target_lines: list[int] | None = None,
) -> dict:
    target_lines = target_lines or CUMUL_DISPLAY_LINES

    work = df.copy()

    # 1) 재공완료 Y 제거
    if "wip_done" in work.columns:
        work = work[work["wip_done"].astype(str).str.upper().str.strip() != "Y"]

    # 2) 라인 필터 (1/3/4/5라인만)
    work = work[work["line_no"].isin(target_lines)].copy()

    # 3) 표시용 슬림 데이터 — 수주건명 바로 오른쪽에 품목명칭 배치
    display_cols = [
        "item_code", "color", "plan_sec", "plan_qty",
        "order_name", "item_name", "ship_date", "line",
    ]
    display_cols = [c for c in display_cols if c in work.columns]
    detail = work[display_cols].rename(columns={
        "item_code": "제품코드", "color": "색상", "plan_sec": "작업시간(초)",
        "plan_qty": "수량", "item_name": "품목명칭", "order_name": "수주건명",
        "ship_date": "출고일자", "line": "라인",
    })

    # 4) 라인(원본 라벨) × 출고일자 — 수량/시간 합쳐진 표
    combined = _build_combined_pivot(work)

    return {
        "detail": detail.reset_index(drop=True),
        "combined": combined,
        "raw_filtered": work.reset_index(drop=True),
    }


def _build_combined_pivot(work: pd.DataFrame) -> pd.DataFrame:
    """라인 × 출고일자 표를 만들되, 각 라인을 (수량, 시간) 2줄로 풀어서 반환한다.

    출력 컬럼: 생산라인, 구분, <출고일자들...>, 합계
    마지막 두 줄은 전체 합계.
    """
    if work.empty:
        return pd.DataFrame(columns=["생산라인", "구분"])

    # ship_date 없는 행은 '재고생산'으로 분류 (전달사항이 '재고생산'인 경우 등)
    w = work.copy()
    w["ship_date"] = w["ship_date"].fillna("재고생산")

    qty = w.pivot_table(index="line", columns="ship_date", values="plan_qty",
                        aggfunc="sum", fill_value=0)
    sec = w.pivot_table(index="line", columns="ship_date", values="plan_sec",
                        aggfunc="sum", fill_value=0)

    if qty.empty:
        return pd.DataFrame(columns=["생산라인", "구분"])

    # 컬럼 순서: 날짜는 오름차순, '재고생산'은 맨 뒤
    date_cols = sorted([c for c in qty.columns if c != "재고생산"])
    if "재고생산" in qty.columns:
        date_cols = date_cols + ["재고생산"]
    qty = qty.reindex(columns=date_cols, fill_value=0)
    sec = sec.reindex(columns=date_cols, fill_value=0)

    # 합계 컬럼
    qty["합계"] = qty.sum(axis=1)
    sec["합계"] = sec.sum(axis=1)

    # 라인 정렬: 라인번호 오름차순
    def _line_key(label: str):
        import re
        m = re.search(r"(\d+)\s*라인", str(label))
        return (int(m.group(1)) if m else 99, str(label))
    ordered_lines = sorted(qty.index, key=_line_key)

    rows = []
    for ln in ordered_lines:
        row_q = {"생산라인": ln, "구분": "수량"}
        row_q.update({c: int(qty.loc[ln, c]) for c in qty.columns})
        rows.append(row_q)
        row_s = {"생산라인": ln, "구분": "시간"}
        row_s.update({c: int(sec.loc[ln, c]) for c in sec.columns})
        rows.append(row_s)

    # 전체 합계
    tot_q = {"생산라인": "합계", "구분": "수량"}
    tot_q.update({c: int(qty[c].sum()) for c in qty.columns})
    rows.append(tot_q)
    tot_s = {"생산라인": "합계", "구분": "시간"}
    tot_s.update({c: int(sec[c].sum()) for c in sec.columns})
    rows.append(tot_s)

    out = pd.DataFrame(rows)
    # 컬럼 순서: 생산라인, 구분, 날짜들..., 재고생산(있을 때), 합계
    col_order = ["생산라인", "구분"] + list(qty.columns)
    return out[col_order]
