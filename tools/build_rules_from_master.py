"""마스터 엑셀 → line_rules.json 자동 생성.

처리 시트 2개:
1) '품목군코드상세' — 소파류 작업자 O/X 매트릭스 (1~8라인 분배 대상)
2) '특정라인 지정' — 반제품 라인(10) 전용 코드 (소파 외 부속)
추가:
- 품목명에 '쿠션·헤드레스트·커넥터·봉제' 포함 코드도 반제품 라인 전용으로 자동 등록.

규칙:
- 품목군코드상세: 작업자 컬럼이 'O'가 아닌 라인은 차단 패턴 등록 (prefix `^코드`).
  반제품 라인은 무조건 차단 → 일반 분배 참여 안 함.
- 특정라인 지정: 이 시트의 코드는 반제품 라인 전용 → 1~8라인 모두 차단.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from core.lines import LINE_WORKERS, WORKER_TO_LINE, LINE_FINISHED  # noqa: E402

MASTER_FILE = ROOT / "품목마스터" / "마감작업자별 생산가능품목_코드목록_v2.xlsx"
RULES_PATH = ROOT / "app" / "storage" / "config" / "line_rules.json"

LINE_9 = LINE_FINISHED  # 반제품 라인 (소파 외 부속 전용)
FINISHED_KEYWORDS = ["쿠션", "헤드레스트", "커넥터", "봉제"]


def collect_general_rules(forbidden: dict[int, set[str]]) -> int:
    """품목군코드상세 시트 처리 — 일반 작업 가능 매트릭스.

    9라인(크리수나)은 무조건 차단 → 일반 분배에서 제외.
    """
    df = pd.read_excel(MASTER_FILE, sheet_name="품목군코드상세", header=0)
    print(f"[품목군코드상세] 행수: {len(df)}")

    code_col = "추출코드" if "추출코드" in df.columns else None
    if not code_col:
        print("  ⚠ '추출코드' 컬럼 없음. 시트 무시.")
        return 0

    count = 0
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if not code or code.lower() == "nan":
            continue
        # 메타 텍스트(괄호 시작 같은 안내문) 노이즈 제외
        if code.startswith("(") or not any(c.isalnum() for c in code):
            continue

        # 일반 작업자 매트릭스 처리 (9라인 제외)
        for worker, line_no in WORKER_TO_LINE.items():
            if line_no == LINE_9:
                continue  # 9라인은 일반 분배 제외 — 무조건 차단
            if worker not in df.columns:
                continue
            cell = row[worker]
            cell_str = str(cell).strip().upper() if pd.notna(cell) else ""
            if cell_str != "O":
                forbidden[line_no].add(f"^{code}")

        # 9라인은 품목군코드상세의 모든 코드 차단 (특정라인 전용)
        forbidden[LINE_9].add(f"^{code}")
        count += 1
    return count


def collect_cushion_rules(forbidden: dict[int, set[str]]) -> int:
    """품목명칭에 반제품 키워드(쿠션·헤드레스트·커넥터·봉제) 포함 코드는 반제품 라인 전용.

    품목군코드상세 + 품목코드_명칭 맵핑 두 소스를 모두 검사. 매칭된 코드를
    1~8라인 차단 + 반제품 라인 허용으로 등록. prefix(^코드) 패턴.
    """
    nineline_codes: set[str] = set()
    count = 0

    def _is_finished(name: str) -> bool:
        return any(kw in name for kw in FINISHED_KEYWORDS)

    # 1) 품목군코드상세 — 추출코드(prefix) + 품목명칭
    df = pd.read_excel(MASTER_FILE, sheet_name="품목군코드상세", header=0).fillna("")
    code_col = "추출코드" if "추출코드" in df.columns else None
    name_col = next((c for c in df.columns if "품목명" in str(c)), None)
    if code_col and name_col:
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            name = str(row[name_col]).strip()
            if not code or code.lower() == "nan":
                continue
            if not _is_finished(name):
                continue
            for line_no in range(1, 9):
                forbidden[line_no].add(f"^{code}")
            nineline_codes.add(f"^{code}")
            count += 1

    # 2) 품목코드_명칭 맵핑 — 정확 코드 + 품목명
    mapping_file = MASTER_FILE.parent / "품목코드_명칭 맵핑.xlsx"
    if mapping_file.exists():
        raw = pd.read_excel(mapping_file, header=None, dtype=str).fillna("")
        header_row = None
        for idx in range(min(5, len(raw))):
            row_vals = [str(v).strip() for v in raw.iloc[idx].tolist()]
            if any("품목코드" in v for v in row_vals) and any("품목명" in v or "명칭" in v for v in row_vals):
                header_row = idx
                break
        if header_row is not None:
            df2 = pd.read_excel(mapping_file, header=header_row, dtype=str).fillna("")
            code_col2 = next((c for c in df2.columns if "품목코드" in str(c)), None)
            name_col2 = next((c for c in df2.columns if ("품목명" in str(c) or "명칭" in str(c))), None)
            if code_col2 and name_col2:
                for _, row in df2.iterrows():
                    code = str(row[code_col2]).strip()
                    name = str(row[name_col2]).strip()
                    if not code or code.lower() == "nan":
                        continue
                    if not _is_finished(name):
                        continue
                    for line_no in range(1, 9):
                        forbidden[line_no].add(f"^{code}")
                    nineline_codes.add(f"^{code}")
                    count += 1

    forbidden[LINE_9] -= nineline_codes
    return count


def collect_special_line_rules(forbidden: dict[int, set[str]]) -> int:
    """특정라인 지정 시트 — 9라인 전용 코드.

    이 시트의 코드는 1~8라인 모두 차단 (9라인에서만 가능).
    9라인의 차단 목록에서는 이 코드들을 제거.
    """
    try:
        df = pd.read_excel(MASTER_FILE, sheet_name="특정라인 지정", header=0)
    except Exception as e:
        print(f"[특정라인 지정] 시트 읽기 실패: {e}")
        return 0
    print(f"[특정라인 지정] 행수: {len(df)}")

    # 첫 컬럼이 품목코드
    code_col = df.columns[0]
    count = 0
    nineline_codes: set[str] = set()
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if not code or code.lower() == "nan" or code == "품목코드":
            continue
        if not any(c.isalnum() for c in code):
            continue

        # 1~8라인 차단 (9라인 외 모두 작업 불가)
        for line_no in range(1, 9):
            forbidden[line_no].add(f"^{code}")
        # 9라인 차단 목록에서는 제거 (9라인만 가능하게)
        nineline_codes.add(f"^{code}")
        count += 1

    # 9라인 차단 목록 정리 — 특정라인 코드는 9라인에서 허용
    forbidden[LINE_9] -= nineline_codes
    return count


def main():
    if not MASTER_FILE.exists():
        print(f"파일 없음: {MASTER_FILE}")
        return 1

    forbidden: dict[int, set[str]] = {ln: set() for ln in LINE_WORKERS.keys()}

    n_general = collect_general_rules(forbidden)
    n_cushion = collect_cushion_rules(forbidden)
    n_special = collect_special_line_rules(forbidden)

    print(f"\n[처리 결과] 일반 코드 {n_general}개, 쿠션 코드 {n_cushion}개, 특정라인 코드 {n_special}개")

    out = {"exact": {}, "pattern": {}}
    for ln, patterns in sorted(forbidden.items()):
        if patterns:
            out["pattern"][str(ln)] = sorted(patterns)

    print("\n[라인별 작업불가 패턴 개수]")
    for ln in sorted(LINE_WORKERS.keys()):
        worker = LINE_WORKERS[ln]
        cnt = len(out["pattern"].get(str(ln), []))
        suffix = " (반제품 전용 - 일반 분배 제외)" if ln == LINE_9 else ""
        print(f"  {ln}라인 ({worker}): {cnt}개 차단 패턴{suffix}")

    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장됨: {RULES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
