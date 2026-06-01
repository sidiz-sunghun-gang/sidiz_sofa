"""분할 락 검증."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.loader import read_grd_excel
from core.daily import distribute_daily
from core.rules import LineRules
from core.policy import GroupPolicy
from core.split import SplitLock, distribute_rows_by_weight

DAILY_XLS = ROOT / "당일분배" / "grd_list_20260523104445.xls"


def main():
    df = read_grd_excel(str(DAILY_XLS))

    print("=" * 70)
    print("[1] 가중치 → 행 분배 단위 테스트")
    print("=" * 70)
    cases = [
        (6, {1: 1, 3: 3, 4: 1, 5: 1}),
        (12, {1: 1, 3: 3, 4: 1, 5: 1}),
        (7, {1: 1, 3: 3, 4: 1, 5: 1}),
        (3, {3: 2, 4: 1}),
    ]
    for n, w in cases:
        res = distribute_rows_by_weight(n, w)
        print(f"  N={n}, weights={w} → {res}")
        # 합 검증
        from collections import Counter
        print(f"    배분: {dict(Counter(res))}")

    print()
    print("=" * 70)
    print("[2] 분배 실행 — 분할 락 없음 (baseline)")
    print("=" * 70)
    res_no = distribute_daily(df, LineRules())
    print(res_no["summary"][["라인", "구분", "총 계획시간(초)", "총 계획량"]].to_string(index=False))

    print()
    print("=" * 70)
    print("[3] 분배 실행 — ACSF0461JN을 1:3:1:1 비율로 락")
    print("=" * 70)
    lock = SplitLock(locks={"ACSF0461JN": {1: 1, 3: 3, 4: 1, 5: 1}})
    res = distribute_daily(df, LineRules(), split_lock=lock)
    print(res["summary"][["라인", "구분", "총 계획시간(초)", "총 계획량"]].to_string(index=False))

    print("\n[ACSF0461JN 행들의 배정라인]")
    d = res["detail"]
    sub = d[d["제품코드"] == "ACSF0461JN"][["제품코드", "수주건명", "수량", "배정라인", "후보라인"]]
    print(sub.to_string(index=False))
    print(f"\n해당 품목 행 수: {len(sub)}")
    print(f"라인별 분포: {sub['배정라인'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
