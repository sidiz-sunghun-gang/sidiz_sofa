"""모듈 동작 스모크 테스트."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.loader import read_grd_excel
from core.cumulative import process_cumulative
from core.daily import distribute_daily
from core.rules import LineRules


DAILY_XLS = ROOT / "당일분배" / "grd_list_20260523104445.xls"
CUMUL_XLS = ROOT / "누적분배" / "grd_list_20260523104729.xls"


def main():
    print("=" * 70)
    print("[누적분배] combined 표")
    print("=" * 70)
    df_c = read_grd_excel(str(CUMUL_XLS))
    res_c = process_cumulative(df_c)
    print(res_c["combined"].to_string(index=False))

    print()
    print("=" * 70)
    print("[당일분배] 8·9라인 제외 확인")
    print("=" * 70)
    df_d = read_grd_excel(str(DAILY_XLS))
    res_d = distribute_daily(df_d, LineRules())

    print("\n[부하 요약]")
    print(res_d["summary"].to_string(index=False))

    print("\n[combined 라인×출고일자]")
    print(res_d["combined"].to_string(index=False))

    print("\n[원본 8·9라인이 분배제외로 표시되는지 detail 확인 (상위 일부)]")
    d = res_d["detail"]
    mask = d["원본라인"].astype(str).str.contains("8라인|9라인", na=False)
    print(d[mask][["제품코드", "원본라인", "배정라인", "후보라인", "작업시간(초)"]].head(10).to_string(index=False))
    print(f"\n8·9라인 행 수: {mask.sum()} (이 행들은 배정라인이 원본 라인을 유지해야 함)")


if __name__ == "__main__":
    main()
