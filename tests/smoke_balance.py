"""수량 우선 + 출고일 균등 분배 검증."""
import sys
from pathlib import Path
import statistics as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.loader import read_grd_excel
from core.daily import distribute_daily
from core.rules import LineRules


DAILY_XLS = ROOT / "당일분배" / "grd_list_20260523104445.xls"


def cv(vals):
    """coefficient of variation = stdev/mean. 작을수록 균등."""
    vals = list(vals)
    m = sum(vals) / len(vals)
    if m == 0:
        return 0.0
    s = st.pstdev(vals)
    return s / m * 100


def main():
    df = read_grd_excel(str(DAILY_XLS))
    res = distribute_daily(df, LineRules())
    summary = res["summary"]
    dist = summary[summary["구분"] == "분배"].copy()

    print("=" * 70)
    print("[1] 라인별 부하 요약 (분배 대상만)")
    print("=" * 70)
    print(dist.to_string(index=False))

    # 인당 수량 / 인당 시간 계산
    dist["인원"] = dist["인원"].astype(int)
    dist["인당 수량"] = dist["총 계획량"] / dist["인원"]
    dist["인당 시간"] = dist["총 계획시간(초)"] / dist["인원"]
    print()
    print("인당 부하 (수량, 시간):")
    print(dist[["라인", "인원", "총 계획량", "인당 수량", "총 계획시간(초)", "인당 시간"]].to_string(index=False))

    cv_qty = cv(dist["인당 수량"])
    cv_sec = cv(dist["인당 시간"])
    print(f"\n인당 수량 변동계수(CV): {cv_qty:.2f}%  (작을수록 균등)")
    print(f"인당 시간 변동계수(CV): {cv_sec:.2f}%")

    # 그룹 단일라인 위반 검사
    detail = res["detail"]
    d2 = detail[detail["후보라인"] != "(분배제외)"]
    grp_ck = d2.groupby("수주건명", dropna=False)["배정라인"].nunique()
    bad = grp_ck[grp_ck > 1]
    print()
    print(f"수주건명 단일라인 위반: {len(bad)}건 (0이면 정상)")

    # 출고일자 × 라인 분포
    print()
    print("=" * 70)
    print("[2] 라인 × 출고일자 — 수량 분포")
    print("=" * 70)
    piv_qty = d2.pivot_table(index="배정라인", columns="출고일자",
                              values="수량", aggfunc="sum", fill_value=0)
    print(piv_qty.to_string())

    # 출고일자별 라인 분산 (CV)
    print("\n출고일자별 라인 수량 변동계수 (작을수록 라인 간 분산 잘 됨):")
    line_count = len(piv_qty.index)
    for date in piv_qty.columns:
        vals = piv_qty[date].tolist()
        if sum(vals) == 0:
            continue
        # 인원 가중 — 인당 부하 기준으로 보려면, 일단 절대 수량 CV
        c = cv(vals)
        # 0이 많을수록 한 라인에 몰린 것
        zeros = sum(1 for v in vals if v == 0)
        print(f"  {date}:  vals={vals}  zeros={zeros}/{line_count}  CV={c:.1f}%")


if __name__ == "__main__":
    main()
