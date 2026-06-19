"""마감작업자별 생산가능품목 엑셀 → line_rules.json 자동 생성.

규칙:
- '품목군코드상세' 시트의 각 행에서 작업자 컬럼이 'O'가 아니면 그 라인의 작업불가 코드
- '추출코드'는 prefix 형태(예: ACSB2904)라 색상 변형 모두 매칭되도록 pattern으로 등록
- pattern 형태: '^<코드>' (코드로 시작하는 모든 품목)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.lines import LINE_WORKERS, WORKER_TO_LINE  # noqa: E402

MASTER_FILE = ROOT / "품목마스터" / "마감작업자별 생산가능품목_코드목록_v2.xlsx"
RULES_PATH = ROOT / "app" / "storage" / "config" / "line_rules.json"


def main():
    if not MASTER_FILE.exists():
        print(f"파일 없음: {MASTER_FILE}")
        return 1

    # 품목군코드상세 시트 — 첫 행이 헤더 (구분/NO/품목군/추출코드/품목명칭/작업자들)
    df = pd.read_excel(MASTER_FILE, sheet_name="품목군코드상세", header=0)
    print(f"시트 행수: {len(df)}")
    print(f"컬럼: {list(df.columns)}")

    # 작업자 컬럼 (이름과 일치)
    worker_cols = {name: name for name in WORKER_TO_LINE.keys() if name in df.columns}
    missing = [n for n in WORKER_TO_LINE.keys() if n not in df.columns]
    if missing:
        print(f"⚠️ 엑셀에 없는 작업자 컬럼: {missing}")

    # 각 라인별로 차단할 prefix 코드 모으기
    forbidden: dict[int, set[str]] = {ln: set() for ln in LINE_WORKERS.keys()}

    code_col = "추출코드" if "추출코드" in df.columns else None
    if not code_col:
        print("'추출코드' 컬럼이 없습니다.")
        return 1

    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if not code or code.lower() == "nan":
            continue
        for worker, line_no in WORKER_TO_LINE.items():
            if worker not in df.columns:
                continue
            cell = row[worker]
            cell_str = str(cell).strip().upper() if pd.notna(cell) else ""
            if cell_str != "O":
                # O가 아니면 해당 라인에서 작업 불가
                forbidden[line_no].add(f"^{code}")

    # JSON 빌드
    out = {"exact": {}, "pattern": {}}
    for ln, patterns in sorted(forbidden.items()):
        if patterns:
            out["pattern"][str(ln)] = sorted(patterns)

    # 요약 출력
    print("\n[라인별 작업불가 패턴 개수]")
    for ln in sorted(LINE_WORKERS.keys()):
        worker = LINE_WORKERS[ln]
        cnt = len(out["pattern"].get(str(ln), []))
        print(f"  {ln}라인 ({worker}): {cnt}개 차단 패턴")

    # 저장
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장됨: {RULES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
