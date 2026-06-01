"""수주건명 그룹 단위 분배 검증."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.loader import read_grd_excel
from core.daily import distribute_daily
from core.rules import LineRules


DAILY_XLS = ROOT / "당일분배" / "grd_list_20260523104445.xls"


def main():
    df = read_grd_excel(str(DAILY_XLS))
    res = distribute_daily(df, LineRules())
    detail = res["detail"]

    # 분배 대상만 (8·9라인 제외)
    dist = detail[detail["후보라인"] != "(분배제외)"].copy()
    print("=" * 70)
    print("[1] 그룹 단위 분배 위반 검사")
    print("=" * 70)
    grp = dist.groupby("수주건명", dropna=False)["배정라인"].nunique()
    bad = grp[grp > 1]
    print(f"수주건명 그룹 수: {len(grp)}")
    print(f"한 라인에 묶이지 않은 그룹 수 (>=2 라인에 흩어진 그룹): {len(bad)}")
    if len(bad) > 0:
        print("⚠️ 위반 그룹들:")
        for k, v in bad.items():
            print(f"  - {k}: {v}개 라인에 흩어짐")
            print(dist[dist["수주건명"] == k][["제품코드", "수주건명", "배정라인"]].to_string(index=False))
    else:
        print("✅ 모든 수주건명 그룹이 단일 라인에 묶임")

    print()
    print("=" * 70)
    print("[2] 라인별 부하 요약")
    print("=" * 70)
    print(res["summary"].to_string(index=False))

    print()
    print("=" * 70)
    print("[3] 다건 그룹 배정 결과 (대표 예시)")
    print("=" * 70)
    multi_grp = dist.groupby("수주건명").size()
    multi_grp = multi_grp[multi_grp >= 2].sort_values(ascending=False).head(8)
    for name in multi_grp.index:
        sub = dist[dist["수주건명"] == name][["제품코드", "수주건명", "작업시간(초)", "배정라인"]]
        total_sec = sub["작업시간(초)"].sum()
        line = sub["배정라인"].iloc[0]
        print(f"\n● {name}  [총 {total_sec:,}초 / {len(sub)}건] → {line}")
        print(sub.to_string(index=False))


if __name__ == "__main__":
    main()
