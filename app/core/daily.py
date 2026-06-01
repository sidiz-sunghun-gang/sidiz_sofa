"""당일분배 분배 알고리즘.

규칙:
- 분배 대상 라인: 1·3·4·5라인 (target_lines)
- 그 외 라인(예: 8라인, 9라인)은 분배하지 않고 원본 라인을 그대로 유지한다.
- **같은 수주건명(order_name)은 반드시 한 라인에 묶어서 배정** (좌/우 단차 등 품질 이유).
- 작업불가 제약: 그룹 내 모든 품목코드가 작업 가능한 라인의 교집합에서만 배정.
- 균등 분배 점수: 인당 가중부하 + 출고일자 쏠림 페널티의 가중합
    score = w_qty * 인당수량 + w_sec * 인당시간 + w_date * 출고일자_쏠림
  기본 가중치: 수량 우선(w_qty=0.5), 출고일 균등(w_date=0.3), 시간(w_sec=0.2).
- 그룹 처리 순서: 수량 내림차순 → 시간 내림차순 → 행 수 내림차순.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .rules import LineRules
from .policy import GroupPolicy
from .split import SplitLock, distribute_rows_by_weight

DAILY_TARGET_LINES = [1, 3, 4, 5]
LINE_HEADCOUNT = {1: 2, 3: 2, 4: 2, 5: 1}

# 기본 가중치 — 수량 우선 + 락 부합도
DEFAULT_WEIGHTS = {"qty": 0.4, "sec": 0.15, "date": 0.2, "lock": 0.25}


def distribute_daily(
    df: pd.DataFrame,
    rules: LineRules,
    *,
    target_lines: list[int] | None = None,
    headcount: Dict[int, int] | None = None,
    weights: Dict[str, float] | None = None,
    group_policy: GroupPolicy | None = None,
    split_lock: SplitLock | None = None,
) -> dict:
    target_lines = target_lines or DAILY_TARGET_LINES
    headcount = headcount or LINE_HEADCOUNT
    wt = {**DEFAULT_WEIGHTS, **(weights or {})}
    policy = group_policy or GroupPolicy()
    lock = split_lock or SplitLock()

    work = df.copy()

    if "plan_sec" not in work.columns:
        work["plan_sec"] = 0
    work["plan_sec"] = pd.to_numeric(work["plan_sec"], errors="coerce").fillna(0)
    if "plan_qty" not in work.columns:
        work["plan_qty"] = 0
    work["plan_qty"] = pd.to_numeric(work["plan_qty"], errors="coerce").fillna(0)

    # 분배 대상과 비대상 분리
    is_target = work["line_no"].isin(target_lines)
    excluded = work[~is_target].copy()
    target = work[is_target].copy()

    # --- 비대상: 원본 라인 그대로 ---
    if not excluded.empty:
        excluded["배정라인"] = excluded["line_no"].apply(
            lambda x: f"{int(x)}라인" if pd.notna(x) else "미지정"
        )
        excluded["후보라인"] = "(분배제외)"

    # --- 대상: 수주건명 그룹 단위 LPT + 인원 가중 분배 ---
    target = target.reset_index(drop=False).rename(columns={"index": "_orig_idx"})

    # === 신규: 품목코드 분할 락 처리 (그룹 LPT보다 먼저) ===
    # 락된 품목코드의 행들을 가중치 비율대로 라인에 강제 배정.
    # 락된 부하는 load_*에 미리 누적해서 이후 자동 분배가 균형을 맞출 수 있게 한다.
    load_sec_pre: Dict[int, float] = {l: 0.0 for l in target_lines}
    load_qty_pre: Dict[int, float] = {l: 0.0 for l in target_lines}
    load_date_qty_pre: Dict[int, Dict[str, float]] = {l: {} for l in target_lines}
    locked_assign: Dict[int, int] = {}  # target.index → 라인번호
    locked_cand_str: Dict[int, str] = {}

    # === 락 적용 정책 ===
    # 단독 행 (수주건명 비어있음 OR 분할 정책 키워드 매칭) → 락 풀에 등록, 강제 비율 분배.
    # 일반 수주건명 그룹의 행은 락 풀에서 제외 → 그룹 LPT의 점수에 락 부합도로 반영.
    # 이유: 같은 수주건명은 좌/우 단차 등 품질 이슈로 같은 라인에 묶여야 함.
    raw_keys_for_lock = (
        target.get("order_name", pd.Series([""] * len(target)))
        .fillna("").astype(str).str.strip()
    )

    def _is_solo_for_lock(idx) -> bool:
        nm = raw_keys_for_lock.loc[idx]
        return (not nm) or policy.should_split(nm)

    if (lock.exact or lock.pattern) and not target.empty:
        match_by_idx: Dict[int, Tuple[str, str]] = {}
        for idx in target.index:
            if not _is_solo_for_lock(idx):
                continue  # 일반 수주건명 그룹은 락 강제 풀 제외
            code = str(target.loc[idx, "item_code"])
            m = lock.find_match(code)
            if m is not None:
                t, key, _w = m
                match_by_idx[idx] = (t, key)

        pools: Dict[Tuple[str, str], List[int]] = {}
        for idx, key in match_by_idx.items():
            pools.setdefault(key, []).append(idx)

        for (lk_type, lk_key), row_idx in pools.items():
            weight_map = lock.exact[lk_key] if lk_type == "exact" else lock.pattern[lk_key]
            allowed_sets = [
                set(rules.allowed_lines_for(str(target.loc[i, "item_code"]), lines=target_lines))
                for i in row_idx
            ]
            allowed = set.intersection(*allowed_sets) if allowed_sets else set(target_lines)
            usable = {l: w for l, w in weight_map.items() if l in allowed and float(w) > 0}
            if not usable:
                continue
            n = len(row_idx)
            line_per_row = distribute_rows_by_weight(n, usable)
            row_sorted = sorted(row_idx, key=lambda i: -float(target.loc[i, "plan_sec"]))
            line_sorted = sorted(line_per_row, key=lambda l: -usable.get(l, 0))
            type_label = "고정" if lk_type == "exact" else f"패턴 {lk_key}"
            cand_text = ",".join(f"{l}라인({type_label})" for l in sorted(usable.keys()))
            for idx, ln in zip(row_sorted, line_sorted):
                locked_assign[idx] = ln
                locked_cand_str[idx] = cand_text
                sec_v = float(target.loc[idx, "plan_sec"])
                qty_v = float(target.loc[idx, "plan_qty"])
                load_sec_pre[ln] += sec_v
                load_qty_pre[ln] += qty_v
                ship_v = target.loc[idx, "ship_date"] if "ship_date" in target.columns else None
                ship_key = ship_v if pd.notna(ship_v) else "미지정"
                load_date_qty_pre[ln][ship_key] = load_date_qty_pre[ln].get(ship_key, 0.0) + qty_v

    # 그룹키: order_name (빈 값/NaN은 행마다 단독 그룹)
    # 분할 정책 키워드(재고/센터/AS 등) 포함 시에도 행마다 단독 그룹으로 풀어서 분산 허용.
    # 락된 행도 단독 그룹 (이후 그룹 처리에서 자동 제외됨)
    raw_keys = target.get("order_name", pd.Series([""] * len(target))).fillna("").astype(str).str.strip()
    solo_marks = pd.Series(
        [f"__solo_{i}__" for i in range(len(target))], index=target.index
    )
    is_empty = raw_keys == ""
    is_splittable = raw_keys.apply(policy.should_split)
    is_locked = target.index.isin(locked_assign.keys())
    target["_group_key"] = raw_keys.where(~(is_empty | is_splittable | is_locked), solo_marks)

    # 그룹 집계: 부하 / 수량 / 교집합 후보 라인 / 출고일자별 분포
    groups = []
    for gkey, gdf in target.groupby("_group_key", sort=False):
        # 락된 행은 이미 배정 결정됨 — 그룹 처리에서 제외
        gdf = gdf[~gdf.index.isin(locked_assign)]
        if gdf.empty:
            continue
        allowed_sets = [
            set(rules.allowed_lines_for(c, lines=target_lines))
            for c in gdf["item_code"].astype(str).tolist()
        ]
        if allowed_sets:
            allowed = sorted(set.intersection(*allowed_sets))
        else:
            allowed = list(target_lines)
        ship_col = gdf.get("ship_date", pd.Series(["미지정"] * len(gdf))).fillna("미지정").astype(str)
        date_qty = gdf.assign(_d=ship_col).groupby("_d")["plan_qty"].sum().to_dict()
        date_sec = gdf.assign(_d=ship_col).groupby("_d")["plan_sec"].sum().to_dict()

        # 그룹 내 락 매칭 → 라인별 선호도 누적 (있으면 점수에 반영)
        lock_pref: Dict[int, float] = {l: 0.0 for l in target_lines}
        has_lock = False
        if lock.exact or lock.pattern:
            for code in gdf["item_code"].astype(str).tolist():
                m = lock.find_match(code)
                if m is None:
                    continue
                _t, _k, w_map = m
                tot_w = sum(float(v) for v in w_map.values() if float(v) > 0)
                if tot_w <= 0:
                    continue
                for l, w in w_map.items():
                    if l in lock_pref and float(w) > 0:
                        lock_pref[l] += float(w) / tot_w
                has_lock = True

        groups.append({
            "key": gkey,
            "indices": gdf.index.tolist(),
            "total_sec": float(gdf["plan_sec"].sum()),
            "total_qty": float(gdf["plan_qty"].sum()),
            "date_qty": {d: float(v) for d, v in date_qty.items()},
            "date_sec": {d: float(v) for d, v in date_sec.items()},
            "allowed": allowed,
            "size": len(gdf),
            "lock_pref": lock_pref if has_lock else None,
        })

    # 정규화 분모: 인당 평균 부하의 스케일을 맞춤
    total_hc = max(1, sum(headcount.get(l, 0) for l in target_lines))
    norm_qty = max(1.0, sum(g["total_qty"] for g in groups) / total_hc)
    norm_sec = max(1.0, sum(g["total_sec"] for g in groups) / total_hc)
    # 출고일별 평균 인당 부하 (수량 기준): 모든 (라인, 날짜) 셀의 평균 수량
    all_dates = set()
    for g in groups:
        all_dates.update(g["date_qty"].keys())
    n_cells = max(1, total_hc * max(1, len(all_dates)))
    norm_date = max(1.0, sum(g["total_qty"] for g in groups) / n_cells)

    # 그룹 처리 순서: 수량 우선 → 시간 → 크기. 큰 그룹부터 좋은 자리 확보.
    groups.sort(key=lambda g: (-g["total_qty"], -g["total_sec"], -g["size"]))

    # 락된 부하를 초기치로 반영 → 자동 분배가 균형을 이미 락된 부하 고려해 결정
    load_sec: Dict[int, float] = {l: load_sec_pre[l] for l in target_lines}
    load_qty: Dict[int, float] = {l: load_qty_pre[l] for l in target_lines}
    load_date_qty: Dict[int, Dict[str, float]] = {
        l: dict(load_date_qty_pre[l]) for l in target_lines
    }

    assign_by_idx: Dict[int, str] = {}
    cand_by_idx: Dict[int, str] = {}

    # 락된 행 먼저 결과에 반영
    for idx, ln in locked_assign.items():
        assign_by_idx[idx] = f"{ln}라인"
        cand_by_idx[idx] = locked_cand_str.get(idx, f"{ln}라인(고정)")

    for g in groups:
        allowed = g["allowed"]
        cand_str = ",".join(f"{l}라인" for l in allowed) if allowed else ""
        if not allowed:
            for idx in g["indices"]:
                assign_by_idx[idx] = "UNASSIGNED"
                cand_by_idx[idx] = cand_str
            continue

        best_line = None
        best_score = None
        lock_pref = g.get("lock_pref")
        lock_total = sum(lock_pref.values()) if lock_pref else 0.0

        for l in allowed:
            hc = max(1, headcount.get(l, 1))
            # 1) 인당 수량 부하 (배정 후)
            s_qty = (load_qty[l] + g["total_qty"]) / hc / norm_qty
            # 2) 인당 시간 부하 (배정 후)
            s_sec = (load_sec[l] + g["total_sec"]) / hc / norm_sec
            # 3) 출고일자 쏠림 페널티
            peak = 0.0
            for d, q in g["date_qty"].items():
                cur = load_date_qty[l].get(d, 0.0)
                peak += (cur + q)
            s_date = peak / hc / norm_date
            # 4) 락 부합도 — 그룹의 락 매칭이 선호하는 라인 쪽 낮은 점수(좋음)
            #    선호 비중이 높을수록 (1 - ratio) → 작음 = 좋음
            if lock_pref is not None and lock_total > 0:
                line_ratio = lock_pref.get(l, 0.0) / lock_total
                s_lock = 1.0 - line_ratio
            else:
                s_lock = 0.0  # 그룹에 락 매칭 없으면 영향 없음

            score = (wt["qty"] * s_qty + wt["sec"] * s_sec
                     + wt["date"] * s_date + wt.get("lock", 0.0) * s_lock)
            if (best_score is None) or (score < best_score) or (
                score == best_score and (best_line is None or l < best_line)
            ):
                best_line = l
                best_score = score

        # 배정 반영
        load_sec[best_line] += g["total_sec"]
        load_qty[best_line] += g["total_qty"]
        for d, q in g["date_qty"].items():
            load_date_qty[best_line][d] = load_date_qty[best_line].get(d, 0.0) + q
        for idx in g["indices"]:
            assign_by_idx[idx] = f"{best_line}라인"
            cand_by_idx[idx] = cand_str

    target["배정라인"] = target.index.map(assign_by_idx)
    target["후보라인"] = target.index.map(cand_by_idx)

    # 원래 행 순서 복원 — 원본 인덱스를 인덱스로 복귀시켜 excluded와 concat 후 sort_index 가능
    target_sorted = (
        target.drop(columns=["_group_key"])
        .set_index("_orig_idx")
        .sort_index()
    )
    target_sorted.index.name = None

    # 합치기 (원래 순서 보존)
    full = pd.concat([target_sorted, excluded], ignore_index=False).sort_index().reset_index(drop=True)

    # 표시용 detail — 수주건명 바로 오른쪽에 품목명칭 배치
    show_cols = ["item_code", "color", "plan_sec", "plan_qty",
                 "order_name", "item_name", "ship_date", "line", "배정라인", "후보라인"]
    show_cols = [c for c in show_cols if c in full.columns]
    detail = full[show_cols].rename(columns={
        "item_code": "제품코드", "color": "색상", "plan_sec": "작업시간(초)",
        "plan_qty": "수량", "item_name": "품목명칭", "order_name": "수주건명",
        "ship_date": "출고일자", "line": "원본라인",
    })

    # 라인별 부하 요약 (대상 + 제외)
    rows = []
    for l in target_lines:
        hc = headcount.get(l, 1)
        rows.append({
            "라인": f"{l}라인", "구분": "분배", "인원": hc,
            "총 계획시간(초)": int(load_sec[l]),
            "총 계획량": int(load_qty[l]),
            "인당 부하(초)": int(load_sec[l] / max(1, hc)),
        })
    # 제외 라인별 합계
    if not excluded.empty:
        ex_grp = excluded.groupby("배정라인", dropna=False).agg(
            plan_sec=("plan_sec", "sum"), plan_qty=("plan_qty", "sum")
        )
        for ln, r in ex_grp.iterrows():
            rows.append({
                "라인": ln, "구분": "제외", "인원": "-",
                "총 계획시간(초)": int(r["plan_sec"]),
                "총 계획량": int(r["plan_qty"]),
                "인당 부하(초)": "-",
            })
    unassigned_n = int((target_sorted["배정라인"] == "UNASSIGNED").sum()) if "배정라인" in target_sorted.columns else 0
    if unassigned_n > 0:
        un = target_sorted[target_sorted["배정라인"] == "UNASSIGNED"]
        rows.append({
            "라인": "미배정", "구분": "오류", "인원": 0,
            "총 계획시간(초)": int(un["plan_sec"].sum()),
            "총 계획량": int(un["plan_qty"].sum()),
            "인당 부하(초)": 0,
        })
    summary = pd.DataFrame(rows)

    # 배정 결과 — 라인 × 출고일자 합쳐진 표 (수량/시간)
    combined = _build_combined_pivot(full)

    return {
        "detail": detail,
        "summary": summary,
        "combined": combined,
        "assigned_df": full,
        "unassigned_count": unassigned_n,
    }


def _build_combined_pivot(full: pd.DataFrame) -> pd.DataFrame:
    """라인 × 출고일자, 라인별 (수량, 시간) 2줄로 펼친 표."""
    if full.empty or "배정라인" not in full.columns:
        return pd.DataFrame(columns=["배정라인", "구분"])
    w = full.copy()
    w["ship_date"] = w["ship_date"].fillna("재고생산") if "ship_date" in w.columns else "재고생산"

    qty = w.pivot_table(index="배정라인", columns="ship_date", values="plan_qty",
                        aggfunc="sum", fill_value=0)
    sec = w.pivot_table(index="배정라인", columns="ship_date", values="plan_sec",
                        aggfunc="sum", fill_value=0)
    if qty.empty:
        return pd.DataFrame(columns=["배정라인", "구분"])

    date_cols = sorted([c for c in qty.columns if c != "재고생산"])
    if "재고생산" in qty.columns:
        date_cols += ["재고생산"]
    qty = qty.reindex(columns=date_cols, fill_value=0)
    sec = sec.reindex(columns=date_cols, fill_value=0)
    qty["합계"] = qty.sum(axis=1)
    sec["합계"] = sec.sum(axis=1)

    import re
    def _key(label: str):
        m = re.search(r"(\d+)\s*라인", str(label))
        return (int(m.group(1)) if m else 99, str(label))
    ordered = sorted(qty.index, key=_key)

    rows = []
    for ln in ordered:
        rq = {"배정라인": ln, "구분": "수량"}
        rq.update({c: int(qty.loc[ln, c]) for c in qty.columns})
        rows.append(rq)
        rs = {"배정라인": ln, "구분": "시간"}
        rs.update({c: int(sec.loc[ln, c]) for c in sec.columns})
        rows.append(rs)
    rows.append({"배정라인": "합계", "구분": "수량", **{c: int(qty[c].sum()) for c in qty.columns}})
    rows.append({"배정라인": "합계", "구분": "시간", **{c: int(sec[c].sum()) for c in sec.columns}})

    return pd.DataFrame(rows)[["배정라인", "구분"] + list(qty.columns)]
