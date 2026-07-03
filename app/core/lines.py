"""라인 ↔ 담당자 매핑 (단일 진실의 원천).

이 파일에서 정의한 매핑이 시스템 전반의 라인 구조를 결정한다.
- 1~8라인: 소파 작업
- 9라인 크리수나: 헤드레스트·쿠션·커넥터·봉제 등 소파 외 부속
- 10라인 반제품: ERP의 '(9라인)반제품' 행이 매핑되는 라벨용 라인 (자동 분배 대상 아님)
- 작업자 이름이 데이터 라벨보다 우선 (예: 데이터 '(4라인) 김진영' → 신규 5라인)
"""
from __future__ import annotations

from typing import Dict, List

# 부속(헤드레스트·쿠션·커넥터·봉제 등) 전용 라인 — 8라인 크리수나
LINE_FINISHED = 8

# ──────────────────────────────────────────────────────────────────────
# 라인 번호 → 담당자 이름
# ──────────────────────────────────────────────────────────────────────
LINE_WORKERS: Dict[int, str] = {
    1: "김민웅",
    2: "황정식",
    3: "김두철",
    4: "라잔",
    5: "김진영",
    6: "김사현",
    7: "이진철",
    8: "크리수나",   # 헤드레스트·쿠션·커넥터·봉제 등 소파 외 부속
    9: "노정문",
    10: "반제품",    # ERP '(9라인)반제품' 표기 → 우리 시스템 10라인 라벨
}

# 역방향 (이름 → 라인 번호)
WORKER_TO_LINE: Dict[str, int] = {v: k for k, v in LINE_WORKERS.items()}

# 분배 대상 라인 — 1~9만 자동 분배 후보 (10라인은 라벨 표시용, ERP 반제품 행이 그대로 매핑됨)
TARGET_LINES: List[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9]

# 인원수 — 모두 1명
LINE_HEADCOUNT: Dict[int, int] = {k: 1 for k in LINE_WORKERS}


# ──────────────────────────────────────────────────────────────────────
# 라인 텍스트 → 라인 번호 해석
# ──────────────────────────────────────────────────────────────────────
def resolve_line_no(line_text) -> int | None:
    """라인 텍스트에서 라인 번호 추출.

    우선순위:
    1) 담당자 이름이 텍스트에 포함되면 그 담당자의 신규 라인 번호 반환
    2) '(N라인)' 또는 'N라인' 패턴 fallback
    3) 둘 다 실패 시 None
    """
    if line_text is None:
        return None
    s = str(line_text).strip()
    if not s or s.lower() == "nan":
        return None

    # 1) 담당자 이름 우선
    for name, ln in WORKER_TO_LINE.items():
        if name in s:
            return ln

    # 2) 라인 번호 패턴 fallback
    import re
    m = re.search(r"(\d+)\s*라인", s)
    if m:
        return int(m.group(1))
    return None


def line_label(line_no: int) -> str:
    """라인 번호 → 표시용 라벨. 예: 1 → '1라인 (김민웅)'."""
    name = LINE_WORKERS.get(line_no)
    return f"{line_no}라인 ({name})" if name else f"{line_no}라인"
