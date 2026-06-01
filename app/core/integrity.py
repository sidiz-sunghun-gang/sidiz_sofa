"""누적분배 + 당일분배 결합 정합성 검증.

목적
- 같은 라인 관점에서 누적/당일 부하를 합쳐서 (수량/시간) 종합 판단.
- 수주건명이 누적과 당일에서 같은 라인에 배정됐는지 일관성 검사.
- 출고일자별 라인 부하 매트릭스 통합.
"""
from __future__ import annotations

import pandas as pd

from .daily import LINE_HEADCOUNT


def _line_no_from_label(label: str) -> int | None:
    import re
    m = re.search(r"(\d+)\s*라인", str(label))
    return int(m.group(1)) if m else None


def build_integrity(
    cumul_detail: pd.DataFrame,
    daily_detail: pd.DataFrame,
    *,
    headcount: dict[int, int] | None = None,
) -> dict:
    """누적분배 detail + 당일분배 detail을 받아 결합 분석 결과를 반환.

    Parameters
    ----------
    cumul_detail : process_cumulative()['detail']  — "라인" 컬럼이 "(1라인) 김민웅" 형태
    daily_detail : distribute_daily()['detail']    — "배정라인" 컬럼이 "1라인" 형태
    """
    headcount = headcount or LINE_HEADCOUNT

    cu = cumul_detail.copy() if cumul_detail is not None else pd.DataFrame()
    da = daily_detail.copy() if daily_detail is not None else pd.DataFrame()

    # 라인 번호 정규화
    if not cu.empty and "라인" in cu.columns:
        cu["line_no"] = cu["라인"].apply(_line_no_from_label)
        cu["line_key"] = cu["line_no"].apply(lambda x: f"{int(x)}라인" if pd.notna(x) else None)
    else:
        cu["line_no"] = pd.Series(dtype="Int64")
        cu["line_key"] = pd.Series(dtype="object")

    if not da.empty and "배정라인" in da.columns:
        da["line_no"] = da["배정라인"].apply(_line_no_from_label)
        da["line_key"] = da["배정라인"].astype(str)
    else:
        da["line_no"] = pd.Series(dtype="Int64")
        da["line_key"] = pd.Series(dtype="object")

    # === 1) 라인 종합 부하 (누적 + 당일) ===
    cu_agg = (
        cu.groupby("line_key", dropna=True)
        .agg(누적_수량=("수량", "sum"), 누적_시간=("작업시간(초)", "sum"))
        if not cu.empty else
        pd.DataFrame(columns=["누적_수량", "누적_시간"])
    )
    da_agg = (
        da.groupby("line_key", dropna=True)
        .agg(당일_수량=("수량", "sum"), 당일_시간=("작업시간(초)", "sum"))
        if not da.empty else
        pd.DataFrame(columns=["당일_수량", "당일_시간"])
    )
    combined_load = cu_agg.join(da_agg, how="outer").fillna(0)
    combined_load.index.name = "라인"

    combined_load["종합_수량"] = (combined_load["누적_수량"] + combined_load["당일_수량"]).astype(int)
    combined_load["종합_시간"] = (combined_load["누적_시간"] + combined_load["당일_시간"]).astype(int)
    combined_load["누적_수량"] = combined_load["누적_수량"].astype(int)
    combined_load["누적_시간"] = combined_load["누적_시간"].astype(int)
    combined_load["당일_수량"] = combined_load["당일_수량"].astype(int)
    combined_load["당일_시간"] = combined_load["당일_시간"].astype(int)
    combined_load = combined_load.reset_index()
    combined_load["라인번호"] = combined_load["라인"].apply(_line_no_from_label)
    combined_load["인원"] = combined_load["라인번호"].apply(
        lambda n: headcount.get(int(n), None) if pd.notna(n) else None
    )

    def _per_capita(row):
        hc = row["인원"]
        if hc and hc > 0:
            return int(row["종합_시간"] / hc)
        return None

    combined_load["인당_종합시간"] = combined_load.apply(_per_capita, axis=1)
    combined_load = combined_load.sort_values("라인번호", na_position="last").reset_index(drop=True)
    combined_load = combined_load[[
        "라인", "인원",
        "누적_수량", "당일_수량", "종합_수량",
        "누적_시간", "당일_시간", "종합_시간",
        "인당_종합시간",
    ]]

    # === 2) 수주건명 라인 일관성 ===
    consistency_rows = []
    if "수주건명" in cu.columns and "수주건명" in da.columns:
        cu_orders = (
            cu.dropna(subset=["line_key"])
            .groupby("수주건명")["line_key"].agg(lambda s: sorted(set(s.dropna())))
            .rename("누적_라인")
        )
        da_orders = (
            da.dropna(subset=["line_key"])
            .groupby("수주건명")["line_key"].agg(lambda s: sorted(set(s.dropna())))
            .rename("당일_라인")
        )
        merged = pd.concat([cu_orders, da_orders], axis=1).dropna(how="all")
        # 두 데이터에 모두 존재하는 수주건만 검증
        both = merged.dropna(how="any")
        for name, row in both.iterrows():
            cset = set(row["누적_라인"] or [])
            dset = set(row["당일_라인"] or [])
            ok = (cset & dset) and not (cset - dset) and not (dset - cset)
            consistency_rows.append({
                "수주건명": str(name) if pd.notna(name) else "(미지정)",
                "누적_라인": ", ".join(row["누적_라인"] or []),
                "당일_라인": ", ".join(row["당일_라인"] or []),
                "일관성": "✅ 일치" if (cset == dset) else (
                    "⚠️ 일부 겹침" if (cset & dset) else "❌ 불일치"
                ),
            })
    consistency = pd.DataFrame(consistency_rows)
    if not consistency.empty:
        # 위반(불일치/일부 겹침) 먼저 정렬
        order = {"❌ 불일치": 0, "⚠️ 일부 겹침": 1, "✅ 일치": 2}
        consistency["__sort"] = consistency["일관성"].map(order)
        consistency = consistency.sort_values("__sort").drop(columns=["__sort"]).reset_index(drop=True)

    # === 3) 출고일자 × 라인 매트릭스 (종합 = 누적 + 당일) ===
    rows = []
    for src, df in (("누적", cu), ("당일", da)):
        if df is None or df.empty:
            continue
        d = df.copy()
        ship_col = "출고일자" if "출고일자" in d.columns else None
        if ship_col is None:
            continue
        d[ship_col] = d[ship_col].fillna("재고생산")
        sub = d.groupby(["line_key", ship_col]).agg(
            수량=("수량", "sum"), 시간=("작업시간(초)", "sum")
        ).reset_index()
        sub["출처"] = src
        rows.append(sub)
    matrix = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["line_key", "출고일자", "수량", "시간", "출처"]
    )

    if not matrix.empty:
        matrix["수량"] = matrix["수량"].fillna(0).astype(int)
        matrix["시간"] = matrix["시간"].fillna(0).astype(int)

    # 종합 매트릭스 — 라인 × 출고일자
    if not matrix.empty:
        piv_qty = matrix.pivot_table(
            index="line_key", columns="출고일자", values="수량",
            aggfunc="sum", fill_value=0,
        )
        piv_sec = matrix.pivot_table(
            index="line_key", columns="출고일자", values="시간",
            aggfunc="sum", fill_value=0,
        )
        # 컬럼 정렬: 날짜 오름차순 + 재고생산 맨 뒤
        date_cols = sorted([c for c in piv_qty.columns if c != "재고생산"])
        if "재고생산" in piv_qty.columns:
            date_cols += ["재고생산"]
        piv_qty = piv_qty.reindex(columns=date_cols, fill_value=0)
        piv_sec = piv_sec.reindex(columns=date_cols, fill_value=0)
        piv_qty["합계"] = piv_qty.sum(axis=1)
        piv_sec["합계"] = piv_sec.sum(axis=1)
        # 행 정렬 (라인번호)
        piv_qty = piv_qty.reindex(
            sorted(piv_qty.index, key=lambda x: (_line_no_from_label(x) or 99, x))
        )
        piv_sec = piv_sec.reindex(piv_qty.index)
    else:
        piv_qty = pd.DataFrame()
        piv_sec = pd.DataFrame()

    # === 4) KPI 요약 ===
    kpi = {
        "총_누적_시간": int(combined_load["누적_시간"].sum()) if not combined_load.empty else 0,
        "총_당일_시간": int(combined_load["당일_시간"].sum()) if not combined_load.empty else 0,
        "총_종합_시간": int(combined_load["종합_시간"].sum()) if not combined_load.empty else 0,
        "총_누적_수량": int(combined_load["누적_수량"].sum()) if not combined_load.empty else 0,
        "총_당일_수량": int(combined_load["당일_수량"].sum()) if not combined_load.empty else 0,
        "총_종합_수량": int(combined_load["종합_수량"].sum()) if not combined_load.empty else 0,
        "일관성_위반": int(((consistency["일관성"] != "✅ 일치").sum())
                          if not consistency.empty else 0),
        "일관성_검증된_수주건수": int(len(consistency)),
    }

    return {
        "combined_load": combined_load,
        "consistency": consistency,
        "matrix_qty": piv_qty,
        "matrix_sec": piv_sec,
        "kpi": kpi,
    }
