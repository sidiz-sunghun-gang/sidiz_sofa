"""분할 정책 적용 전/후 비교."""
import sys
from pathlib import Path
import statistics as st_

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.loader import read_grd_excel
from core.daily import distribute_daily
from core.rules import LineRules
from core.policy import GroupPolicy


DAILY_XLS = ROOT / "당일분배" / "grd_list_20260523104445.xls"


def cv(vals):
    vals = list(vals)
    m = sum(vals) / len(vals) if vals else 0
    if m == 0:
        return 0.0
    return st_.pstdev(vals) / m * 100


def summarize(label: str, res: dict):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    print(res["summary"].to_string(index=False))
    detail = res["detail"]
    d2 = detail[detail["후보라인"] != "(분배제외)"]
    piv = d2.pivot_table(index="배정라인", columns="출고일자",
                          values="수량", aggfunc="sum", fill_value=0)
    print("\n[라인 × 출고일자 — 수량]")
    print(piv.to_string())
    # CV
    print("\n출고일자별 라인 수량 CV:")
    for d in piv.columns:
        vals = piv[d].tolist()
        z = sum(1 for v in vals if v == 0)
        print(f"  {d}: {vals}  zeros={z}  CV={cv(vals):.1f}%")
    # 그룹 단일라인 위반
    bad = d2.groupby("수주건명", dropna=False)["배정라인"].nunique()
    bad = bad[bad > 1]
    print(f"\n분할(>=2라인 흩어진) 그룹 수: {len(bad)}")
    for k, v in bad.items():
        print(f"  - {k}: {v}개 라인")


def main():
    df = read_grd_excel(str(DAILY_XLS))

    # 기본 정책 (분할 키워드: 재고/센터/AS/매출외/반품/내작)
    summarize("[정책 ON] 기본 분할 키워드 적용", distribute_daily(df, LineRules(), group_policy=GroupPolicy()))

    # 정책 OFF
    empty_policy = GroupPolicy(split_keywords=[])
    summarize("[정책 OFF] 모든 수주건명 그룹 유지 (이전 동작)", distribute_daily(df, LineRules(), group_policy=empty_policy))


if __name__ == "__main__":
    main()
