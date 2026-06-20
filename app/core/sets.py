"""셋트 구분 — 마스터 '셋트구분' 시트의 (품목코드, 색상) 묶음 관리.

수주취소가 잦은 품목은 출고일 기준으로 수주건명을 관리하기 때문에,
수주건명 그룹핑 대신 셋트번호로 묶어 한 라인에 배정한다.

같은 셋트번호의 행들은 같은 (출고일자, 셋트번호) 단위로 묶여 한 라인에 배정.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd


@dataclass
class SetGroups:
    # (품목코드, 색상) → 셋트번호
    by_code_color: Dict[Tuple[str, str], int] = field(default_factory=dict)

    def lookup(self, item_code: str, color: str) -> int | None:
        if not item_code:
            return None
        key = (str(item_code).strip(), str(color or "").strip())
        return self.by_code_color.get(key)

    def __bool__(self) -> bool:
        return bool(self.by_code_color)


def load_set_groups(master_path: Path | str, sheet: str = "셋트구분") -> SetGroups:
    """마스터 엑셀의 '셋트구분' 시트를 읽어 (코드, 색상) → 셋트번호 매핑 생성.

    시트 구조: 셋트구분 | 품목코드 | 색상 | 품목명칭
    빈 행은 셋트 사이 구분선 — 무시.
    """
    p = Path(master_path)
    if not p.exists():
        return SetGroups()
    try:
        df = pd.read_excel(p, sheet_name=sheet, header=0, dtype=str).fillna("")
    except (ValueError, FileNotFoundError):
        return SetGroups()

    set_col = code_col = color_col = None
    for c in df.columns:
        s = str(c).strip()
        if "셋트" in s and set_col is None:
            set_col = c
        elif "품목코드" in s and code_col is None:
            code_col = c
        elif "색상" in s and color_col is None:
            color_col = c
    if not (set_col and code_col and color_col):
        return SetGroups()

    mapping: Dict[Tuple[str, str], int] = {}
    for _, row in df.iterrows():
        set_v = str(row[set_col]).strip()
        code = str(row[code_col]).strip()
        color = str(row[color_col]).strip()
        if not (set_v and code):
            continue
        try:
            set_no = int(float(set_v))
        except (TypeError, ValueError):
            continue
        mapping[(code, color)] = set_no
    return SetGroups(by_code_color=mapping)
