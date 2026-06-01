"""품목 마스터 — 품목코드 → 품목명칭 매핑.

주로 UI 표시 보조용 (분할 락 요약표/카드 헤더에 이름 함께 노출).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import pandas as pd


@dataclass
class ItemMaster:
    items: Dict[str, str] = field(default_factory=dict)

    # ----------------------------------------------------------------
    # 조회
    # ----------------------------------------------------------------
    def name(self, item_code: str) -> str:
        if not item_code:
            return ""
        return self.items.get(str(item_code), "") or ""

    def has(self, item_code: str) -> bool:
        return str(item_code or "") in self.items

    def __len__(self) -> int:
        return len(self.items)

    # ----------------------------------------------------------------
    # 직렬화
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"items": dict(self.items)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "ItemMaster":
        if not d:
            return cls()
        items: Dict[str, str] = {}
        for k, v in (d.get("items") or {}).items():
            ks = str(k).strip()
            vs = str(v).strip() if v is not None else ""
            if ks and vs and vs.lower() != "nan":
                items[ks] = vs
        return cls(items=items)


def load_item_master(path: Path) -> ItemMaster:
    if not path.exists():
        return ItemMaster()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ItemMaster.from_dict(json.load(f))
    except Exception:
        return ItemMaster()


def save_item_master(path: Path, master: ItemMaster) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(master.to_dict(), f, ensure_ascii=False, indent=2)


_HEADER_KEYWORDS = {
    "품목코드", "item_code", "code",
    "품목명", "품목명칭", "품목명▼", "item_name", "name",
}


def _detect_header_row(path: Path, max_rows: int = 10) -> int:
    """파일 앞부분을 훑어 헤더 행 위치를 자동 감지. 못 찾으면 0."""
    ext = path.suffix.lower()
    try:
        if ext == ".csv":
            preview = pd.read_csv(path, header=None, nrows=max_rows)
        else:
            preview = pd.read_excel(path, header=None, nrows=max_rows)
    except Exception:
        return 0
    keywords_lower = {k.lower() for k in _HEADER_KEYWORDS}
    for i in range(len(preview)):
        cells = [str(v).strip().lower() for v in preview.iloc[i].dropna()]
        if any(c in keywords_lower for c in cells):
            return i
    return 0


def _read_with_smart_header(path: Path) -> pd.DataFrame | None:
    """헤더 위치 자동 감지 후 DataFrame 반환. 모든 시트 시도."""
    ext = path.suffix.lower()
    header_row = _detect_header_row(path)
    try:
        if ext == ".csv":
            return pd.read_csv(path, header=header_row)
        # 엑셀은 시트가 여러 개일 수 있음 — 모든 시트를 시도해 매핑 가능한 첫 시트 반환
        xls = pd.ExcelFile(path)
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(path, sheet_name=sheet, header=header_row)
            except Exception:
                continue
            # 헤더에 우리가 원하는 컬럼이 있는지 확인
            cols_lower = {str(c).strip().lower() for c in df.columns}
            if any(k in cols_lower for k in {"품목코드", "item_code", "code"}):
                return df
        # 못 찾으면 첫 시트 반환
        return pd.read_excel(path, sheet_name=0, header=header_row)
    except Exception:
        return None


def load_master_from_folder(folder: Path) -> tuple[ItemMaster, list[str]]:
    """폴더 내 모든 .xlsx / .csv 파일을 읽어 ItemMaster로 병합.

    헤더 행 위치를 자동 감지하여 첫 행이 빈 행이거나 안내 텍스트여도 정상 인식.
    여러 시트가 있으면 '품목코드' 컬럼을 가진 시트를 우선 선택.

    Returns: (master, loaded_file_names)
    같은 코드가 여러 파일에 있으면 먼저 발견된 항목이 유지된다.
    """
    if not folder.exists():
        return ItemMaster(), []

    items: Dict[str, str] = {}
    loaded: list[str] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".xlsx", ".xls", ".csv"):
            continue
        df = _read_with_smart_header(path)
        if df is None or df.empty:
            continue
        try:
            sub = item_master_from_dataframe(df)
        except Exception:
            continue
        for c, n in sub.items.items():
            items.setdefault(c, n)
        loaded.append(path.name)
    return ItemMaster(items=items), loaded


def item_master_from_dataframe(df: pd.DataFrame) -> ItemMaster:
    """엑셀/CSV에서 (item_code, item_name) 매핑 추출.

    지원 컬럼명: item_code / 품목코드 / code,  item_name / 품목명 / 품목명칭 / name
    """
    if df is None or df.empty:
        return ItemMaster()
    cols = {c.lower(): c for c in df.columns}
    code_col = (cols.get("item_code") or cols.get("품목코드") or cols.get("code"))
    name_col = (
        cols.get("item_name") or cols.get("품목명") or cols.get("품목명칭")
        or cols.get("품목명▼") or cols.get("name")
    )
    if not code_col or not name_col:
        raise ValueError(
            "파일에 'item_code' 와 'item_name' (또는 '품목코드' / '품목명' / '품목명칭') 컬럼이 필요합니다."
        )
    items: Dict[str, str] = {}
    for _, row in df.iterrows():
        c = str(row[code_col]).strip()
        n = str(row[name_col]).strip()
        if c and n and c.lower() != "nan" and n.lower() != "nan":
            # 같은 코드 중복 시 첫 항목 유지 (덮어쓰지 않음)
            items.setdefault(c, n)
    return ItemMaster(items=items)


_SEPARATORS = ("_", "ㅣ", "|")


def _cleanup_tail(s: str) -> str:
    """끝에 어색하게 남는 공백·특수문자를 정리.

    예: '(리커버)사티 1인 (' → '(리커버)사티 1인'
         '밀로 2인 (우) ' → '밀로 2인 (우)'
    """
    if not s:
        return s
    # 끝의 공백/괄호 열림/구두점 제거
    s = s.rstrip(" \t(<[{/\\-·,·:;|ㅣ")
    return s.strip()


def _short_name(name: str) -> str:
    """단일 품목명에서 첫 구분자(_ / ㅣ / |) 앞까지 잘라 핵심만 추출.

    예: '보눔 암리스_프리미엄 레더|아크레_샤모아' → '보눔 암리스'
    """
    if not name:
        return ""
    indices = [name.find(s) for s in _SEPARATORS]
    valid = [i for i in indices if i > 0]
    if valid:
        return _cleanup_tail(name[:min(valid)])
    return _cleanup_tail(name)


def exact_short_name(master: ItemMaster, code: str) -> str:
    """exact 코드 → 짧은 품목명(첫 구분자 앞까지). 마스터에 없으면 경고 텍스트."""
    name = master.name(code)
    if name:
        return _short_name(name)
    # 마스터가 비어있으면 (= 마스터 자체 미구성) 빈 문자열
    if len(master) == 0:
        return ""
    # 마스터는 있는데 해당 코드만 없음
    return "⚠️ 마스터에 코드 없음"


def pattern_common_name(master: ItemMaster, pattern: str) -> str:
    """정규식 패턴 매칭 품목들의 **공통 명칭** + 매칭 수.

    동작:
    1) 매칭 품목명 수집
    2) Longest Common Prefix 계산
    3) 첫 구분자(_ / ㅣ / |) 앞까지 잘라 핵심 단위로 정리
    4) 결과 + " (외 N개)" 형태로 반환

    예) 패턴 ^ACSB3091 매칭 → ['밀로 라지 쿠션_프리미엄 레더…', '밀로 라지 쿠션_하이엔드 레더…']
        LCP = '밀로 라지 쿠션_'  → 자르기 후 '밀로 라지 쿠션'  → '밀로 라지 쿠션 (외 1개)'
    """
    if not master.items or not pattern:
        return ""
    try:
        regex = re.compile(pattern)
    except re.error:
        return ""

    names: List[str] = []
    matched_codes: List[str] = []
    for code, name in master.items.items():
        if regex.search(code):
            matched_codes.append(code)
            if name:
                names.append(name)

    if not matched_codes:
        return "⚠️ 마스터 매칭 0건"
    if not names:
        return f"매칭 {len(matched_codes)}개 (이름 없음)"

    # Longest Common Prefix
    prefix = names[0]
    for s in names[1:]:
        while prefix and not s.startswith(prefix):
            prefix = prefix[:-1]
        if not prefix:
            break

    short_prefix = _short_name(prefix)
    short_prefix = _cleanup_tail(short_prefix)

    total = len(matched_codes)

    # 1) LCP가 충분히 길면 그대로 사용
    if len(short_prefix) >= 2:
        if total == 1:
            return short_prefix
        return f"{short_prefix} (외 {total - 1}개)"

    # 2) LCP가 너무 짧으면 다수결 — 각 명칭의 첫 단위 빈도수로 대표명 채택
    from collections import Counter
    shorts = [_short_name(n) for n in names]
    shorts = [s for s in shorts if s and len(s) >= 2]
    if shorts:
        counter = Counter(shorts)
        most_common, cnt = counter.most_common(1)[0]
        variants = len(counter)
        if variants == 1:
            return f"{most_common} (외 {total - 1}개)"
        # 변종이 있음을 알림
        return f"{most_common} (외 {total - 1}개, 명칭 {variants}종)"

    return f"매칭 {total}개"


def pattern_preview(master: ItemMaster, pattern: str, max_n: int = 3) -> str:
    """[Deprecated] pattern_common_name을 우선 사용. 호환을 위해 유지."""
    return pattern_common_name(master, pattern)
