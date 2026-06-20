"""9라인 구조 전환 후 종합 검증.

1) 작업불가 규칙 — 위반 여부
2) 수주건명 그룹 정책 — 위반 여부
3) 분할 락 — 적용 효과 & 필요성
4) 균등성 — 라인별 부하 편차
"""
import sys
import statistics as st_
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core import storage
from core.loader import read_grd_excel
from core.daily import distribute_daily
from core.cumulative import process_cumulative
from core.rules import load_rules
from core.policy import load_policy
from core.split import load_split_lock, SplitLock
from core.lines import LINE_WORKERS


def cv(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return 0.0
    m = sum(vals) / len(vals)
    if m == 0:
        return 0.0
    return st_.pstdev(vals) / m * 100


def main():
    print("=" * 70)
    print("9라인 구조 종합 검증")
    print("=" * 70)

    rules = load_rules(storage.RULES_PATH)
    policy = load_policy(storage.GROUP_POLICY_PATH)
    lock = load_split_lock(storage.SPLIT_LOCK_PATH)

    print(f"\n[규칙 상태]")
    print(f"  작업불가 패턴: {sum(len(v) for v in rules.pattern.values())}개")
    print(f"  분할 락 (exact / pattern): {len(lock.exact)} / {len(lock.pattern)}개")
    print(f"  그룹 정책 분할 키워드: {policy.split_keywords}")

    # 데이터 로드 — 누적 또는 당일
    raw_da = storage.load_latest_bytes("daily")
    raw_cu = storage.load_latest_bytes("cumulative")
    if raw_da:
        df = read_grd_excel(raw_da)
        src = "당일분배"
    elif raw_cu:
        df = read_grd_excel(raw_cu)
        src = "누적분배 (대체)"
    else:
        print("\n분배할 데이터 없음. 종료.")
        return

    print(f"\n사용 데이터: {src} — 총 {len(df)}행")
    print(f"line_no 분포: {df['line_no'].value_counts(dropna=False).sort_index().to_dict()}")

    # ──────────────────────────────────────────────
    # [1] 분할 락 OFF 분배 — 기본 시나리오
    # ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[1] 분할 락 OFF — 작업불가 규칙 + 그룹 정책만으로 분배")
    print("=" * 70)
    res_off = distribute_daily(df, rules, group_policy=policy, split_lock=SplitLock())
    summary_off = res_off["summary"]
    detail_off = res_off["detail"]
    dist_off = summary_off[summary_off["구분"] == "분배"]
    print("\n[라인별 부하]")
    print(dist_off[["라인", "총 계획시간(초)", "총 계획량"]].to_string(index=False))

    cv_qty = cv(dist_off["총 계획량"].tolist())
    cv_sec = cv(dist_off["총 계획시간(초)"].tolist())
    print(f"\n인당 부하 편차 (CV): 수량 {cv_qty:.1f}%  /  시간 {cv_sec:.1f}%")

    # 작업불가 규칙 위반 체크
    print("\n[작업불가 규칙 위반 검사]")
    violations = []
    d = detail_off[detail_off["배정라인"].astype(str).str.match(r"\d+라인")]
    for _, row in d.iterrows():
        code = str(row["제품코드"])
        ln_str = str(row["배정라인"]).replace("라인", "").strip()
        try:
            ln = int(ln_str)
        except ValueError:
            continue
        allowed = rules.allowed_lines_for(code, lines=list(LINE_WORKERS.keys()))
        if ln not in allowed:
            violations.append((code, ln, allowed))
    print(f"  위반 건수: {len(violations)} (0이어야 정상)")
    if violations[:3]:
        for code, ln, allowed in violations[:3]:
            print(f"  ⚠ {code} → {ln}라인 배정 (허용: {allowed})")

    # 그룹 위반 체크
    print("\n[수주건명 그룹 위반 검사]")
    grp = d.groupby("수주건명", dropna=False)["배정라인"].nunique()
    bad = grp[grp > 1]
    bad = bad[~bad.index.astype(str).str.contains("재고|센터|AS|매출외|반품|내작", na=False, regex=True)]
    print(f"  일반 수주건 중 여러 라인 분산: {len(bad)}건 (0 권장, 분할 정책으로 일부 허용)")

    # 미배정 (작업불가 너무 빡빡해서 아무 라인도 못 받는 경우)
    unassigned = (detail_off["배정라인"] == "UNASSIGNED").sum() if "배정라인" in detail_off.columns else 0
    print(f"\n[미배정 (어디서도 작업 불가)]: {unassigned}건")

    # ──────────────────────────────────────────────
    # [2] 분할 락 적용 시 비교 (현재 lock에 있는 것)
    # ──────────────────────────────────────────────
    if lock.exact or lock.pattern:
        print("\n" + "=" * 70)
        print("[2] 현재 분할 락 적용 시")
        print("=" * 70)
        res_on = distribute_daily(df, rules, group_policy=policy, split_lock=lock)
        dist_on = res_on["summary"][res_on["summary"]["구분"] == "분배"]
        print("\n[라인별 부하 — 락 적용]")
        print(dist_on[["라인", "총 계획시간(초)", "총 계획량"]].to_string(index=False))
        print(f"CV(수량/시간): {cv(dist_on['총 계획량'].tolist()):.1f}% / {cv(dist_on['총 계획시간(초)'].tolist()):.1f}%")
    else:
        print("\n[2] 현재 등록된 분할 락 없음 — 비교 생략")

    # ──────────────────────────────────────────────
    # [3] 라인별 작업 가능 품목 분포
    # ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[3] 라인별 데이터 수용 가능 범위 분석")
    print("=" * 70)
    print("\n각 라인이 현재 데이터에서 작업 가능한 행 수:")
    for ln, worker in LINE_WORKERS.items():
        codes = df["item_code"].astype(str)
        allowed_mask = codes.apply(
            lambda c: ln in rules.allowed_lines_for(c, lines=list(LINE_WORKERS.keys()))
        )
        cnt = int(allowed_mask.sum())
        print(f"  {ln}라인 ({worker}): 가능 {cnt}/{len(df)}행 ({cnt/len(df)*100:.0f}%)")


if __name__ == "__main__":
    main()
